"""Bounded dependency health probes for PGL."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx
import redis
from fastapi import APIRouter
from sqlalchemy import text

from ..config import Settings, get_settings
from ..database import engine

router = APIRouter(tags=["health"])
_PROBE_TIMEOUT_SECONDS = 2.0
_STATE_RANK = {"healthy": 0, "degraded": 1, "unconfigured": 1, "unavailable": 2}


def _host(url: str) -> str:
    return urlparse(url).hostname or "unknown"


def _result(name: str, host: str, state: str, started: float) -> dict[str, Any]:
    return {
        "name": name,
        "host": host,
        "state": state,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


async def _probe_http(name: str, base_url: str) -> dict[str, Any]:
    started = time.perf_counter()
    base = base_url.rstrip("/")
    try:
        timeout = httpx.Timeout(_PROBE_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.get(f"{base}/health")
            if response.status_code == 404:
                response = await client.get(f"{base}/protocol.json")
        state = "healthy" if 200 <= response.status_code < 300 else "degraded"
    except Exception:  # noqa: BLE001 - dependency probes must never raise
        state = "unavailable"
    return _result(name, _host(base_url), state, started)


async def _probe_database() -> dict[str, Any]:
    started = time.perf_counter()

    def check() -> None:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(asyncio.to_thread(check), timeout=_PROBE_TIMEOUT_SECONDS)
        state = "healthy"
    except Exception:  # noqa: BLE001 - dependency probes must never raise
        state = "unavailable"
    return _result("database", "configured", state, started)


async def _probe_redis(name: str, url: str) -> dict[str, Any]:
    started = time.perf_counter()

    def check() -> None:
        client = redis.Redis.from_url(
            url,
            socket_connect_timeout=_PROBE_TIMEOUT_SECONDS,
            socket_timeout=_PROBE_TIMEOUT_SECONDS,
        )
        client.ping()

    try:
        await asyncio.wait_for(asyncio.to_thread(check), timeout=_PROBE_TIMEOUT_SECONDS)
        state = "healthy"
    except Exception:  # noqa: BLE001 - dependency probes must never raise
        state = "unavailable"
    return _result(name, _host(url), state, started)


def _unconfigured(name: str) -> dict[str, Any]:
    return {"name": name, "host": "unconfigured", "state": "unconfigured", "latency_ms": 0.0}


@router.get("/health/dependencies")
async def dependency_health() -> dict[str, Any]:
    settings: Settings = get_settings()
    http_dependencies = [
        ("capi", settings.capi_backend_url),
        ("ollama", os.getenv("OLLAMA_BASE_URL") or "http://ollama:11434"),
    ]

    probes = [
        _probe_database(),
        *(
            _probe_http(name, url) if url else asyncio.sleep(0, result=_unconfigured(name))
            for name, url in http_dependencies
        ),
        (
            _probe_redis("redis", settings.redis_url)
            if settings.redis_url
            else asyncio.sleep(0, result=_unconfigured("redis"))
        ),
    ]
    checks = list(await asyncio.gather(*probes))

    overall = max(checks, key=lambda check: _STATE_RANK[check["state"]])["state"]
    return {"status": overall, "dependencies": checks}
