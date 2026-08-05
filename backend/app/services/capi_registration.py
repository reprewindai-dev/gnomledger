import httpx
import logging
import asyncio
from backend.app.config import Settings

logger = logging.getLogger(__name__)

async def register_with_capi(settings: Settings) -> None:
    """Registers Gnomledger capabilities with the cAPI Universal USB layer."""
    if not settings.capi_backend_url:
        logger.info("[cAPI] Registration skipped: capi_backend_url is not set.")
        return
        
    url = f"{settings.capi_backend_url.rstrip('/')}/api/v1/registry/register"
    headers = {"Content-Type": "application/json"}
    if settings.capi_api_key:
        headers["Authorization"] = f"Bearer {settings.capi_api_key}"
        
    payload = {
        "service_name": "gnomledger",
        "capabilities": ["pgl_ledger", "x402_settlement", "verification"],
        "telemetry_supported": True
    }
    
    import socket
    from urllib.parse import urlparse
    
    # DNS Fallback logic for gaierror Name resolution
    parsed = urlparse(url)
    try:
        # Try to resolve the hostname explicitly to catch DNS errors early
        socket.gethostbyname(parsed.hostname)
    except socket.gaierror:
        logger.warning(f"[cAPI] DNS resolution failed for {parsed.hostname}. Falling back to internal Docker network (capi-container).")
        # Swap hostname for 'capi-container' (default Coolify internal name)
        url = url.replace(parsed.hostname, "capi-container")

    for attempt in range(5):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=5.0)
                if response.status_code in (200, 201):
                    logger.info("[cAPI] Successfully registered Gnomledger with cAPI.")
                    return
                else:
                    logger.warning(f"[cAPI] Failed to register: {response.text}")
        except Exception as e:
            logger.error(f"[cAPI] Error registering with cAPI (attempt {attempt + 1}): {type(e).__name__} - {e}")
            
        await asyncio.sleep(5)
