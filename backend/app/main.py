from __future__ import annotations

import logging
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from .config import get_settings
from .database import init_database
from .routes import create_api_router
from .schemas import ErrorResponse, HealthResponse
from .services.x402_service import build_discovery_manifest
from .utils import utc_now


def _configure_logging() -> None:
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    yield


def _build_app() -> FastAPI:
    settings = get_settings()
    _configure_logging()
    app = FastAPI(
        title=settings.app_name,
        version="1.1.0",
        lifespan=lifespan,
    )
    app.include_router(create_api_router())

    @app.get("/.well-known/x402")
    def x402_discovery() -> dict:
        # Zero-auth, machine-readable pricing manifest. Any agent can fetch
        # this to learn what's payable here and how, per the x402 spec
        # convention of serving discovery at .well-known.
        return build_discovery_manifest()

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

    @app.get("/health", tags=["health"], response_model=HealthResponse)
    async def health_check():
        return HealthResponse(status="ok", timestamp=utc_now())

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
