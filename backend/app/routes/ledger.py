from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, require_role
from ..public_proof import PublicLedgerProofResponse, to_public_ledger_proof
from ..schemas import (
    CheckpointVerifyResponse,
    LedgerChainVerifyRequest,
    LedgerCheckpoint,
    LedgerEventCreate,
    LedgerEventResponse,
    PGLRequestContext,
)
from ..services.audit_bundle_service import AuditBundleService
from ..services.ledger_service import LedgerService
from ..services.principal import describe_principal
from ..services.signing_service import get_signer

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
    ctx: OperatorContext,
) -> LedgerEventResponse:
    if payload.event_type == "decommission":
        # A decommission event must coincide with the status change and record its actor.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="decommission events are written only by POST /api/v1/agents/{agent_id}/decommission",
        )
    service = LedgerService(db)
    try:
        return service.log_event(payload, account_id=ctx.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/agents/{agent_id}", response_model=list[LedgerEventResponse])
def get_agent_history(
    agent_id: str,
    db: DbSession,
    ctx: ViewerContext,
    limit: int = Query(default=200, ge=1, le=500),
    cursor: int | None = Query(default=None, ge=1),
) -> list[LedgerEventResponse]:
    service = LedgerService(db)
    try:
        return service.get_agent_history(
            agent_id=agent_id, limit=limit, cursor=cursor, account_id=ctx.account_id
        )
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
    ctx: ViewerContext,
) -> LedgerChainVerifyRequest:
    service = LedgerService(db)
    try:
        _, payload = service.verify_chain(agent_id, account_id=ctx.account_id)
        return LedgerChainVerifyRequest(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/checkpoint", response_model=LedgerCheckpoint)
def get_agent_checkpoint(
    agent_id: str,
    db: DbSession,
    ctx: ViewerContext,
) -> LedgerCheckpoint:
    """Signed {agent_id, event_count, head_event_hash, issued_at}. An outside party keeps it
    and later detects truncation or rewrite with POST /ledger/checkpoints/verify."""
    try:
        return LedgerCheckpoint(
            **LedgerService(db).issue_checkpoint(agent_id, account_id=ctx.account_id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/audit-bundle")
def get_agent_audit_bundle(
    agent_id: str,
    db: DbSession,
    ctx: ViewerContext,
) -> dict:
    """One signed JSON document for an auditor: agent, every genome version, the signed
    certificate, the full event chain, a fresh signed checkpoint, verification results and
    the public signing key. bundle_signature covers every other field."""
    try:
        return AuditBundleService(db).build(
            agent_id, account_id=ctx.account_id, generated_by=describe_principal(db, ctx)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/checkpoints/verify", response_model=CheckpointVerifyResponse)
def verify_checkpoint(
    checkpoint: LedgerCheckpoint,
    db: DbSession,
    # Public route - intentionally no auth. Chain state is evaluated only for checkpoints
    # carrying this ledger's valid signature, and only booleans are returned.
) -> CheckpointVerifyResponse:
    return CheckpointVerifyResponse(**LedgerService(db).verify_checkpoint(checkpoint))


@router.get("/signing-key")
def get_signing_key() -> dict:
    """Public, no auth. Same document as /.well-known/pgl-signing-key, served under /api so
    deployments that only route /api/* (Vercel) expose it too."""
    return get_signer().public_descriptor()


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
