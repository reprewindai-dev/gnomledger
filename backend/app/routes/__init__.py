from fastapi import APIRouter

from . import agents, ledger, lineage, billing

__all__ = ["agents", "ledger", "lineage", "billing", "create_api_router"]


def create_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(agents.router, prefix="/agents", tags=["agents"])
    router.include_router(ledger.router, prefix="/ledger", tags=["ledger"])
    router.include_router(lineage.router, prefix="/lineage", tags=["lineage"])
    router.include_router(billing.router, prefix="/billing", tags=["billing"])
    return router
