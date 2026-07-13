from fastapi import APIRouter

from .admin import router as admin_router
from .agents import router as agents_router
from .billing import router as billing_router
from .incidents import router as incidents_router
from .integrations import router as integrations_router
from .ledger import router as ledger_router
from .lineage import router as lineage_router
from .notary import router as notary_router
from .reminders import router as reminders_router


def create_api_router() -> APIRouter:
    """Factory used by main.py — returns the fully assembled /api/v1 router."""
    api_router = APIRouter(prefix="/api/v1")
    api_router.include_router(admin_router)
    api_router.include_router(agents_router)
    api_router.include_router(billing_router)
    api_router.include_router(incidents_router)
    api_router.include_router(integrations_router, prefix="/integrations")
    api_router.include_router(ledger_router)
    api_router.include_router(lineage_router)
    api_router.include_router(notary_router)
    api_router.include_router(reminders_router)
    return api_router


# Keep legacy alias so any code that does `from .routes import api_router` still works
api_router = create_api_router()
