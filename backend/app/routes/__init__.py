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

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(admin_router)
api_router.include_router(agents_router)
api_router.include_router(billing_router)
api_router.include_router(incidents_router)
api_router.include_router(integrations_router)
api_router.include_router(ledger_router)
api_router.include_router(lineage_router)
api_router.include_router(notary_router)
api_router.include_router(reminders_router)


def create_api_router() -> APIRouter:
    """
    main.py calls this as a factory (create_api_router()), but only the
    module-level api_router variable existed — a genuine pre-existing bug,
    unrelated to x402. Added as a thin wrapper so the app can actually boot.
    """
    return api_router
