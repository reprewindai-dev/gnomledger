from fastapi import APIRouter, status

from .admin import router as admin_router
from .agents import create_agent, list_agents
from .agents import router as agents_router
from .billing import router as billing_router
from .incidents import router as incidents_router
from .integrations import router as integrations_router
from .ledger import router as ledger_router
from .lineage import router as lineage_router
from .notary import router as notary_router
from .reminders import router as reminders_router
from ..schemas import AgentDetailResponse, AgentResponse


def create_api_router() -> APIRouter:
    """Factory used by main.py — returns the fully assembled /api/v1 router."""
    api_router = APIRouter(prefix="/api/v1")

    # Documented contract (README, bundled UI, CAPPO client): /admin/*, /agents/*, /billing/*.
    api_router.include_router(admin_router, prefix="/admin")
    api_router.include_router(agents_router, prefix="/agents")
    # The agents collection lives at "/" inside its router, which the prefix turns into
    # "/agents/". Serve "/agents" too, without a redirect, since httpx-based callers do not
    # follow redirects by default.
    api_router.add_api_route(
        "/agents",
        list_agents,
        methods=["GET"],
        response_model=list[AgentDetailResponse],
        include_in_schema=False,
    )
    api_router.add_api_route(
        "/agents",
        create_agent,
        methods=["POST"],
        response_model=AgentResponse,
        status_code=status.HTTP_201_CREATED,
        include_in_schema=False,
    )
    api_router.include_router(billing_router, prefix="/billing")
    api_router.include_router(incidents_router)
    api_router.include_router(integrations_router, prefix="/integrations")
    api_router.include_router(ledger_router, prefix="/ledger")
    api_router.include_router(lineage_router, prefix="/lineage")
    api_router.include_router(notary_router)
    api_router.include_router(reminders_router)

    # Legacy unprefixed mounts, kept so existing callers do not break. The agents router
    # goes last: its GET /{agent_id} catch-all matches any single segment, and when it was
    # mounted first it shadowed GET /usage (billing) and GET /capabilities (main.py).
    api_router.include_router(admin_router, include_in_schema=False)
    api_router.include_router(billing_router, include_in_schema=False)
    api_router.include_router(agents_router, include_in_schema=False)
    return api_router


# Keep legacy alias so any code that does `from .routes import api_router` still works
api_router = create_api_router()
