"""PGL protocol discovery endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["protocol"])

MANIFEST: dict[str, Any] = {
    "service": "gnomledger",
    "repo": "reprewindai-dev/gnomledger",
    "role": "evidence/provenance ledger",
    "version": "1.1.0",
    "base_url": "https://pgl.veklom.com",
    "health": "/health",
    "dependencies": "/health/dependencies",
    "auth_mode": "api-key",
    "status": "NOT_VERIFIED",
    "verification": {
        "source_contract": "CONFIGURED",
        "runtime": "NOT_VERIFIED",
        "required_evidence": [
            "deployed_commit_provenance",
            "container_listener_8001",
            "http_health",
            "protocol_identity",
            "traefik_route",
            "capi_registration",
        ],
    },
    "capabilities": [
        "issue_agent_certificates",
        "record_ledger_events",
        "verify_ledger_chains",
        "retrieve_lineage",
        "fork_agent_lineage",
    ],
    "capability_endpoints": {
        "issue_agent_certificates": "POST /api/v1/agents",
        "record_ledger_events": "POST /api/v1/ledger/events",
        "verify_ledger_chains": "GET /api/v1/ledger/agents/{agent_id}/verify",
        "retrieve_lineage": "GET /api/v1/lineage/tree/{agent_id}",
        "fork_agent_lineage": "POST /api/v1/lineage/fork",
    },
    "links": {
        "pgl": "https://pgl.veklom.com/protocol.json",
        "capi": "https://capi.veklom.com/protocol.json",
        "cappo": "https://cappo.veklom.com/protocol.json",
        "byos": "https://api.veklom.com/protocol.json",
    },
}


class IntrospectQuery(BaseModel):
    query: str


@router.get("/protocol.json", include_in_schema=False)
async def get_protocol_manifest() -> dict[str, Any]:
    return MANIFEST


@router.post("/protocol/introspect", include_in_schema=False)
async def introspect_capabilities(body: IntrospectQuery) -> dict[str, Any]:
    query = body.query.lower()
    capabilities = MANIFEST["capabilities"]
    matches = [capability for capability in capabilities if query == "*" or query in capability]
    return {
        "query": body.query,
        "matches": matches,
        "total": len(matches),
        "auth_mode": MANIFEST["auth_mode"],
        "status": MANIFEST["status"],
        "verification": MANIFEST["verification"],
        "links": MANIFEST["links"],
    }
