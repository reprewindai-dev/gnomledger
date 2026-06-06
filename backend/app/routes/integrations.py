from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, require_role
from ..schemas import VeklmAdapterSnapshot
from ..services.adapter_service import AdapterService

router = APIRouter()


@router.get("/vekml/agents/{agent_id}/snapshot", response_model=VeklmAdapterSnapshot)
def get_vekml_agent_snapshot(
    agent_id: str,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> VeklmAdapterSnapshot:
    service = AdapterService(db)
    try:
        return service.get_vekml_snapshot(account_id=ctx.account_id, agent_id=agent_id)
    except ValueError as exc:
        message = str(exc).lower()
        status_code = status.HTTP_404_NOT_FOUND if "unknown" in message or "not found" in message else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
