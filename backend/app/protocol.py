from fastapi import APIRouter
from datetime import datetime, timezone
from typing import Any, Dict

router = APIRouter(tags=["protocol"])

@router.get("/protocol.json")
def get_protocol() -> Dict[str, Any]:
    return {
        "service": "gnomledger",
        "repo": "reprewindai-dev/gnomledger",
        "role": "settlement-ledger",
        "version": "2026.07",
        "base_url": "https://pgl.veklom.com",
        "health": "/health",
        "dependencies": "/health/dependencies",
        "auth_mode": "bearer",
        "capabilities": ["identity-rag", "evidence-ledger", "settlement"],
        "links": {
            "cappo": "https://capi.veklom.com/protocol.json",
            "ledger": "https://ledger.veklom.com/protocol.json",
            "interlink": "https://interlink.veklom.com/protocol.json",
            "core": "https://api.veklom.com/protocol.json"
        },
        "status": "ok"
    }

@router.post("/protocol/introspect")
def introspect_protocol(payload: dict) -> dict:
    return {
        "status": "ok",
        "matched_capabilities": ["identity-rag", "evidence-ledger", "settlement"],
        "routing_info": {"base_url": "https://pgl.veklom.com"}
    }

@router.get("/health")
def healthcheck() -> dict:
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

@router.get("/health/dependencies")
async def health_dependencies() -> dict:
    return {
        "status": "degraded",
        "reason": "dependency health endpoint not fully wired yet"
    }
