from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, require_role
from ..pgl.evidence_validator import PGLEvidenceValidator
from ..pgl.errors import PGLEvidenceError
from ..public_proof import PublicLedgerProofResponse, to_public_ledger_proof
from ..schemas import LedgerChainVerifyRequest, LedgerEventCreate, LedgerEventResponse
from ..services.ledger_service import LedgerService

router = APIRouter()


@router.post("/events", response_model=LedgerEventResponse, status_code=status.HTTP_201_CREATED)
def create_ledger_event(
    payload: LedgerEventCreate,
    db: Session = Depends(get_db),
    _ctx=Depends(require_role("operator", "admin", "owner")),
) -> LedgerEventResponse:
    # RTV-1B: WID-5 Identity Chain Enforcement
    # LedgerEventCreate validates that details matches PreExecutionAuthorizationDetails /
    # PostExecutionAttestationDetails (via model_validator). After that passes,
    # provenance is a dict with typed WID-5 identity chain fields.
    # The WID-5 validator then enforces format, hash integrity, and truth discipline.
    # Schema failure = 422. Identity chain violation = 403 with PGL_* denial code.
    if payload.event_type in ["pre_execution_authorization", "post_execution_attestation"]:
        validator = PGLEvidenceValidator()
        provenance_dict = payload.details.get("provenance") or {}
        # provenance is a PGLIdentityChainProvenance Pydantic model serialized as dict
        if hasattr(provenance_dict, "model_dump"):
            provenance_dict = provenance_dict.model_dump()
        elif not isinstance(provenance_dict, dict):
            provenance_dict = dict(provenance_dict) if provenance_dict else {}
        try:
            validator.validate_append(payload=provenance_dict, is_genesis=False)
        except PGLEvidenceError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.to_evidence())

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
        _, payload = service.verify_chain(agent_id)
        return LedgerChainVerifyRequest(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/proof/{hash}", response_model=PublicLedgerProofResponse)
def get_event_by_hash(
    hash: str,
    db: Session = Depends(get_db),
    # Public route - intentionally no auth. Response is limited to non-sensitive
    # hash lookup metadata and does not expose the underlying event payload.
) -> PublicLedgerProofResponse:
    service = LedgerService(db)
    try:
        event = service.get_event_by_hash(hash)
        return to_public_ledger_proof(event)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
