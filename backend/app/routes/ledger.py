from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, require_role
from ..public_proof import PublicLedgerProofResponse, to_public_ledger_proof
from ..schemas import (
    LedgerChainVerifyRequest,
    LedgerEventCreate,
    LedgerEventResponse,
    PGLRequestContext,
)
from ..services.ledger_service import LedgerService

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]
OperatorContext = Annotated[
    PGLRequestContext,
    Depends(require_role("operator", "admin", "owner")),
]
ViewerContext = Annotated[
    PGLRequestContext,
    Depends(require_role("viewer", "operator", "admin", "owner")),
]


@router.post("/events", response_model=LedgerEventResponse, status_code=status.HTTP_201_CREATED)
def create_ledger_event(
    payload: LedgerEventCreate,
    db: DbSession,
    _ctx: OperatorContext,
) -> LedgerEventResponse:
    service = LedgerService(db)
    try:
        return service.log_event(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/agents/{agent_id}", response_model=list[LedgerEventResponse])
def get_agent_history(
    agent_id: str,
    db: DbSession,
    _ctx: ViewerContext,
    limit: int = Query(default=200, ge=1, le=500),
    cursor: int | None = Query(default=None, ge=1),
) -> list[LedgerEventResponse]:
    service = LedgerService(db)
    try:
        return service.get_agent_history(agent_id=agent_id, limit=limit, cursor=cursor)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/events/{event_id}", response_model=LedgerEventResponse)
def get_ledger_event(
    event_id: str,
    db: DbSession,
    ctx: ViewerContext,
) -> LedgerEventResponse:
    """Retrieve one exact authenticated ledger event, including its evidence payload."""
    try:
        return LedgerService(db).get_event_by_id(event_id, account_id=ctx.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/verify", response_model=LedgerChainVerifyRequest)
def verify_agent_chain(
    agent_id: str,
    db: DbSession,
    _ctx: ViewerContext,
) -> LedgerChainVerifyRequest:
    service = LedgerService(db)
    try:
        _, payload = service.verify_chain(agent_id)
        return LedgerChainVerifyRequest(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/proof/{hash}", response_model=PublicLedgerProofResponse)
def get_event_by_hash(
    hash: str,
    db: DbSession,
    # Public route - intentionally no auth. Response is limited to non-sensitive
    # hash lookup metadata and does not expose the underlying event payload.
) -> PublicLedgerProofResponse:
    service = LedgerService(db)
    try:
        event = service.get_event_by_hash(hash)
        return to_public_ledger_proof(event)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
