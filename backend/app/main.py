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

    return app


def create_app() -> FastAPI:
    return _build_app()


app = create_app()
