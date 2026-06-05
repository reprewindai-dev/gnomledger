from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, require_role
from ..schemas import LedgerChainVerifyRequest, LedgerEventCreate, LedgerEventResponse
from ..services.ledger_service import LedgerService

router = APIRouter()


@router.post("/events", response_model=LedgerEventResponse, status_code=status.HTTP_201_CREATED)
def create_ledger_event(
    payload: LedgerEventCreate,
    db: Session = Depends(get_db),
    _ctx=Depends(require_role("operator", "admin", "owner")),
) -> LedgerEventResponse:
    service = LedgerService(db)
    try:
        return service.log_event(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/agents/{agent_id}", response_model=list[LedgerEventResponse])
def get_agent_history(
    agent_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    cursor: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    _ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> list[LedgerEventResponse]:
    service = LedgerService(db)
    try:
        return service.get_agent_history(agent_id=agent_id, limit=limit, cursor=cursor)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/verify", response_model=LedgerChainVerifyRequest)
def verify_agent_chain(
    agent_id: str,
    db: Session = Depends(get_db),
    _ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> LedgerChainVerifyRequest:
    service = LedgerService(db)
    try:
        valid, payload = service.verify_chain(agent_id)
        return LedgerChainVerifyRequest(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
