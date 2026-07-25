from __future__ import annotations

import asyncio
import logging
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import hashlib
import json

from .config import get_settings
from .database import check_database, init_database
from .routes import create_api_router
from .schemas import ErrorResponse, HealthResponse
from .services.x402_service import build_discovery_manifest
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
    cors_origins = list(settings.cors_origins)
    if settings.frontend_origin and settings.frontend_origin not in cors_origins:
        cors_origins.append(settings.frontend_origin)
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(create_api_router())

    @app.get("/.well-known/x402", tags=["discovery"])
    @app.get("/.well-known/x402.json", tags=["discovery"])
    def x402_discovery() -> dict:
        # Zero-auth, machine-readable pricing manifest. Any agent can fetch
        # this to learn what's payable here and how, per the x402 spec
        # convention of serving discovery at .well-known.
        return build_discovery_manifest()

    @app.post("/tools/mint_settlement_evidence", tags=["mcp"])
    def mint_settlement_evidence(payload: dict) -> dict:
        """Return deterministic evidence for a machine-supplied settlement payload."""
        payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        evidence_hash = hashlib.sha256(payload_bytes).hexdigest()
        logger.info("Anchored settlement evidence: %s", evidence_hash)
        return {"status": "anchored", "evidence_hash": evidence_hash, "payload": payload}

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

    @app.get("/api/v1/capabilities", tags=["discovery"])
    async def capabilities_check():
        return {
            "service": "gnomledger",
            "contract_version": "pgl-execution-v1",
            "event_types": [
                "pre_execution_authorization",
                "post_execution_attestation",
                "violation"
            ],
            "supports_idempotency": True,
            "supports_chain_verification": True
        }

    from .protocol import router as protocol_router
    app.include_router(protocol_router)

    return app


def create_app() -> FastAPI:
    return _build_app()


app = create_app()
