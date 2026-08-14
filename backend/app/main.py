from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

try:
    from veklom_amphoteric import AmphotericRouter, create_mcp_endpoints
except ImportError:  # Optional integration is not present in a clean checkout.
    AmphotericRouter = None
    create_mcp_endpoints = None

from .config import get_settings
from .database import check_database, init_database
from .routes import create_api_router
from .routes.health_dependencies import router as health_dependencies_router
from .routes.protocol import router as protocol_router
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

    from backend.app.services.capi_registration import maintain_capi_registration

    capi_stop = asyncio.Event()
    capi_task = asyncio.create_task(maintain_capi_registration(get_settings(), capi_stop))

    try:
        yield
    finally:
        capi_stop.set()
        if not capi_task.done():
            capi_task.cancel()
        try:
            await capi_task
        except asyncio.CancelledError:
            pass
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
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://veklom.com", "https://api.veklom.com"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.include_router(create_api_router())
    app.include_router(protocol_router)
    app.include_router(health_dependencies_router)

    if AmphotericRouter is not None and create_mcp_endpoints is not None:
        amphoteric = AmphotericRouter()

        @amphoteric.tool(
            "validate_settlement_evidence_structure",
            "Compute an experimental content digest; this does not anchor or prove settlement evidence",
        )
        def validate_settlement_evidence_structure(payload: dict) -> dict:
            payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            content_digest = hashlib.sha256(payload_bytes).hexdigest()
            return {
                "status": "EXPERIMENTAL_STRUCTURE_VALIDATION",
                "content_digest": content_digest,
                "anchored": False,
                "zk_verified": False,
                "durable_evidence": False,
                "limitations": [
                    "No verifier circuit or key provenance is configured.",
                    "No public-input binding or replay protection is performed.",
                    "No Lockerphycer, CAPPO, or durable Gnomledger anchoring is performed.",
                ],
            }

        app.include_router(amphoteric.router)
        create_mcp_endpoints(app, amphoteric)
    else:
        logger.warning("veklom_amphoteric is unavailable; optional MCP tools were not registered")

    @app.middleware("http")
    async def request_size_limit(request: Request, call_next):
        if request.headers.get("content-length"):
            content_length = int(request.headers.get("content-length"))
            if content_length > 10 * 1024 * 1024:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "Request too large"}
                )
        return await call_next(request)

    @app.middleware("http")
    async def request_identity(request: Request, call_next):
        request_id = request.headers.get(settings.request_id_header, secrets.token_urlsafe(12))
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        response.headers["x-processing-ms"] = str(int((time.perf_counter() - start) * 1000))
        return response

    @app.exception_handler(Exception)
    async def global_exception_handler(_: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(detail="Internal Server Error").model_dump(),
        )

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
            detail="database unavailable",
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
                detail="database unavailable",
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
                "violation",
            ],
            "supports_idempotency": True,
            "supports_chain_verification": True,
        }

    @app.get("/.well-known/x402.json", tags=["discovery"])
    async def x402_discovery():
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "NOT_VERIFIED",
                "service": "gnomledger",
                "x402": "NOT_IMPLEMENTED",
                "pricing": "NOT_CONFIGURED",
                "payment_destination": "NOT_CONFIGURED",
                "facilitator": "NOT_VERIFIED",
                "routes": [],
                "required_evidence": [
                    "deployed commit provenance",
                    "configured facilitator and payment destination",
                    "negative and replay-protection tests",
                    "successful durable settlement evidence in Gnomledger",
                ],
            },
        )

    return app


def create_app() -> FastAPI:
    return _build_app()


app = create_app()
