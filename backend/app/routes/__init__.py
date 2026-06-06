from fastapi import APIRouter

from . import admin, agents, billing, integrations, lineage, ledger

__all__ = ["admin", "agents", "ledger", "lineage", "billing", "integrations", "create_api_router"]


def create_api_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(agents.router, prefix="/agents", tags=["agents"])
    router.include_router(ledger.router, prefix="/ledger", tags=["ledger"])
    router.include_router(lineage.router, prefix="/lineage", tags=["lineage"])
    router.include_router(billing.router, prefix="/billing", tags=["billing"])
    router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
    router.include_router(admin.router, prefix="/admin", tags=["admin"])
    return router
