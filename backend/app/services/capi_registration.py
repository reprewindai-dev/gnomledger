"""cAPI registration and liveness maintenance for Gnomledger."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from backend.app.config import Settings

logger = logging.getLogger(__name__)

REGISTRATION_TIMEOUT_SECONDS = 5.0
RETRY_SECONDS = 5.0
DEFAULT_REGISTRY_TTL_MS = 300_000


def _heartbeat_interval_seconds(settings: Settings) -> float:
    raw_ttl = getattr(settings, "CAPI_REGISTRY_TTL_MS", os.getenv("CAPI_REGISTRY_TTL_MS", DEFAULT_REGISTRY_TTL_MS))
    try:
        ttl_ms = int(raw_ttl)
    except (TypeError, ValueError):
        ttl_ms = DEFAULT_REGISTRY_TTL_MS
    if ttl_ms <= 0:
        ttl_ms = DEFAULT_REGISTRY_TTL_MS
    return max(ttl_ms / 1_000 * 0.8, 0.001)


async def _wait_for_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        pass


def _registry_url(settings: Settings, path: str) -> str | None:
    base_url = (settings.capi_backend_url or "").strip()
    return f"{base_url.rstrip('/')}{path}" if base_url else None


def _headers(settings: Settings) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.capi_api_key:
        headers["Authorization"] = f"Bearer {settings.capi_api_key}"
    return headers


def _registration_payload() -> dict[str, object]:
    return {
        "service_name": "gnomledger",
        "capabilities": ["pgl_ledger", "verification"],
        "telemetry_supported": True,
    }


async def register_with_capi(
    settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> bool:
    """Register Gnomledger once; callers decide when a failed attempt is retried."""
    url = _registry_url(settings, "/api/v1/registry/register")
    if not url:
        logger.info("cAPI registration skipped: capi_backend_url is not configured")
        return False

    try:
        async with httpx.AsyncClient(timeout=REGISTRATION_TIMEOUT_SECONDS, transport=transport) as client:
            response = await client.post(url, json=_registration_payload(), headers=_headers(settings))
    except httpx.HTTPError as exc:
        logger.warning("cAPI registration failed (%s)", type(exc).__name__)
        return False

    if response.status_code in (200, 201):
        logger.info("Gnomledger registered with cAPI")
        return True
    logger.warning("cAPI registration rejected with status %s", response.status_code)
    return False


async def heartbeat_until_missing(
    settings: Settings, stop: asyncio.Event, transport: httpx.AsyncBaseTransport | None = None
) -> bool:
    """Refresh Gnomledger registration until cAPI reports it missing or shutdown begins."""
    url = _registry_url(settings, "/api/v1/registry/heartbeat")
    if not url:
        return False

    while not stop.is_set():
        await _wait_for_stop(stop, _heartbeat_interval_seconds(settings))
        if stop.is_set():
            return False
        try:
            async with httpx.AsyncClient(timeout=REGISTRATION_TIMEOUT_SECONDS, transport=transport) as client:
                response = await client.post(url, json={"service_name": "gnomledger"}, headers=_headers(settings))
        except httpx.HTTPError as exc:
            logger.warning("cAPI heartbeat failed (%s)", type(exc).__name__)
            continue

        if 200 <= response.status_code < 300:
            continue
        if response.status_code == 404:
            logger.info("Gnomledger cAPI registration is missing; re-registering")
            return True
        logger.warning("cAPI heartbeat rejected with status %s", response.status_code)
    return False


async def maintain_capi_registration(
    settings: Settings, stop: asyncio.Event, transport: httpx.AsyncBaseTransport | None = None
) -> None:
    """Keep Gnomledger registered without treating transport health as authority."""
    while not stop.is_set():
        if await register_with_capi(settings, transport):
            await heartbeat_until_missing(settings, stop, transport)
        else:
            await _wait_for_stop(stop, RETRY_SECONDS)
