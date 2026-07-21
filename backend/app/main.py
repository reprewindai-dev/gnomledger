from __future__ import annotations

import asyncio
import logging
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from .config import get_settings
from .database import check_database, init_database
from .routes import create_api_router
from .schemas import ErrorResponse, HealthResponse
from .utils import utc_now


logger = logging.getLogger(__name__)
DATABASE_RETRY_SECONDS = 90
DATABASE_RETRY_INTERVAL_SECONDS = 5


def _configure_logging() -> None:
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.database_ready = False
    app.state.database_error = "database initialization has not completed"

    async def initialize_database_until_ready() -> None:
        deadline = time.monotonic() + DATABASE_RETRY_SECONDS
        while True:
            try:
                await asyncio.to_thread(init_database)
                await asyncio.to_thread(check_database)
                app.state.database_ready = True
                app.state.database_error = None
                logger.info("PGL database schema is ready")
                return
            except Exception as exc:  # pragma: no cover - exact DB driver errors vary by deployment
                app.state.database_ready = False
                app.state.database_error = str(exc)
                if time.monotonic() >= deadline:
                    logger.error("PGL database is unavailable after startup retry window: %s", exc)
                    return
                logger.warning("PGL database is not ready yet; retrying: %s", exc)
                await asyncio.sleep(DATABASE_RETRY_INTERVAL_SECONDS)

    database_task = asyncio.create_task(initialize_database_until_ready())
    
    from backend.app.services.capi_registration import register_with_capi
    from backend.app.config import get_settings
    capi_task = asyncio.create_task(register_with_capi(get_settings()))
    
    try:
        yield
    finally:
        if capi_task and not capi_task.done():
            capi_task.cancel()
        if not database_task.done():
            database_task.cancel()
            try:
                await database_task
            except asyncio.CancelledError:
                pass


def _build_app() -> FastAPI:
    settings = get_settings()
    _configure_logging()
    app = FastAPI(
        title=settings.app_name,
        version="1.1.0",
        lifespan=lifespan,
    )
    app.include_router(create_api_router())

    @app.middleware("http")
    async def request_identity(request: Request, call_next):
        request_id = request.headers.get(settings.request_id_header, secrets.token_urlsafe(12))
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        response.headers["x-processing-ms"] = str(int((time.perf_counter() - start) * 1000))
        return response

    @app.exception_handler(ValueError)
    async def handle_value_error(_: Request, exc: ValueError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(detail=str(exc)).model_dump(),
        )

    @app.get("/health/live", tags=["health"], response_model=HealthResponse)
    async def liveness_check():
        return HealthResponse(status="ok", timestamp=utc_now())

    @app.get("/health", tags=["health"], response_model=HealthResponse)
    async def health_check():
        if getattr(app.state, "database_ready", False):
            return HealthResponse(status="ok", timestamp=utc_now(), database="ready")
        return HealthResponse(
            status="degraded",
            timestamp=utc_now(),
            database="unavailable",
            detail=getattr(app.state, "database_error", "database unavailable"),
        )

    @app.get("/health/ready", tags=["health"], response_model=HealthResponse)
    async def readiness_check():
        if getattr(app.state, "database_ready", False):
            return HealthResponse(status="ok", timestamp=utc_now(), database="ready")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=HealthResponse(
                status="error",
                timestamp=utc_now(),
                database="unavailable",
                detail=getattr(app.state, "database_error", "database unavailable"),
            ).model_dump(mode="json"),
        )

    @app.get("/.well-known/x402.json", tags=["discovery"])
    async def x402_discovery():
        return {
            "x402_version": 2,
            "provider": "GnomLedger — Programmable Governance Layer",
            "network": "eip155:8453",
            "payTo": "0xCC34553b4e6332ffb9C1b61E22436ACA53113D1d",
            "currency": "USDC",
            "identity": {
                "veklom_id_app": "6a20f24cc341f72c2f573eb5",
                "veklom_id_wallet": "0x3a74772e925b54F7dAD7FD95c9Ba30825033f970",
                "verification_domain": "veklom-id.vercel.app",
            },
            "routes": [
                {
                    "route": "POST /api/v1/agents",
                    "price": "$0.010",
                    "description": "Register a new agent identity and issue a birth certificate with PGL hash.",
                    "tags": ["pgl", "agent", "identity", "register", "veklom"],
                },
                {
                    "route": "GET /api/v1/agents/{id}",
                    "price": "$0.003",
                    "description": "Retrieve agent genome, birth certificate, and lifecycle state.",
                    "tags": ["pgl", "agent", "genome", "veklom"],
                },
                {
                    "route": "GET /api/v1/agents/{id}/lineage",
                    "price": "$0.005",
                    "description": "Trace full agent lineage tree — forks, ancestry, and provenance chain.",
                    "tags": ["pgl", "lineage", "provenance", "veklom"],
                },
                {
                    "route": "GET /api/v1/ledger",
                    "price": "$0.005",
                    "description": "Query the append-only life ledger with hash-chain integrity verification.",
                    "tags": ["pgl", "ledger", "audit", "hash-chain", "veklom"],
                },
                {
                    "route": "POST /api/v1/agents/{id}/fork",
                    "price": "$0.015",
                    "description": "Fork an agent genome, creating a new derived agent with ancestry link.",
                    "tags": ["pgl", "fork", "genome", "agent", "veklom"],
                },
            ],
            "discovery": {
                "bazaar": "https://bazaar.cdp.coinbase.com",
                "openapi": "https://pgl.veklom.com/docs",
                "veklom_id": "https://veklom-id.vercel.app",
            },
        }

    return app


def create_app() -> FastAPI:
    return _build_app()


app = create_app()
