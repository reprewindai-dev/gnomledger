from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, require_role
from ..schemas import LedgerChainVerifyRequest, LedgerEventCreate, LedgerEventResponse
from ..services.ledger_service import LedgerService
from ..services.merkle_service import MerkleTree
from .. import models

router = APIRouter(prefix="/ledger")


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


@router.get("/batch/{batch_id}/proof")
def get_batch_proof(
    batch_id: str,
    event_id: str = Query(..., description="The event_id to get the proof for"),
    db: Session = Depends(get_db),
    _ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
):
    # Fetch all events in this batch
    events = list(
        db.query(models.LedgerEvent)
        .filter(models.LedgerEvent.batch_id == batch_id, models.LedgerEvent.tier == 4)
        .order_by(models.LedgerEvent.id.asc())
        .all()
    )
    if not events:
        raise HTTPException(status_code=404, detail="Batch not found")

    target_idx = next((i for i, e in enumerate(events) if e.event_id == event_id), None)
    if target_idx is None:
        raise HTTPException(status_code=404, detail="Event not found in this batch")

    leaves = [e.event_hash for e in events]
    tree = MerkleTree(leaves)
    proof = tree.get_proof(target_idx)
    root = tree.get_root()

    return {
        "batch_id": batch_id,
        "event_id": event_id,
        "merkle_root": root,
        "proof": proof
    }
