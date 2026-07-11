from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..dependencies import get_db, require_role, require_apikey_or_x402
from ..config import get_settings
from ..schemas import (
    CertificateDownloadResponse,
    AgentCreateRequest,
    AgentDetailResponse,
    AgentResponse,
    GenomePayload,
    GenomeUpdateRequest,
)
from ..services.certificate_service import CertificateService
from ..services.genome_service import GenomeService
from .. import models

router = APIRouter(prefix="/agents")


@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: AgentCreateRequest,
    db: Session = Depends(get_db),
    ctx=Depends(require_apikey_or_x402("/api/v1/agents", "POST")),
) -> AgentResponse:
    account_id = ctx.account_id
    if account_id == 0:
        # x402 pay-per-call caller with no account of their own. They still
        # need a real account row for the agent/lineage/quota FKs. This
        # requires a reserved "x402 pool" account to exist in the DB —
        # NOT YET CREATED. Until a migration seeds it (see BLOCKERS below),
        # anonymous x402 calls to this endpoint will fail here rather than
        # silently attach to a wrong/fake account.
        settings = get_settings()
        reserved_id = getattr(settings, "x402_pool_account_id", None)
        if not reserved_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "x402 payment verified, but no reserved pool account is configured "
                    "to hold anonymous agents. Set X402_POOL_ACCOUNT_ID after seeding it."
                ),
            )
        account_id = reserved_id

    service = CertificateService(db)
    try:
        return service.register_agent(payload, account_id=account_id)
    except ValueError as exc:
        status_code = status.HTTP_402_PAYMENT_REQUIRED if "quota" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/", response_model=list[AgentDetailResponse])
def list_agents(
    limit: int = Query(default=100, ge=1, le=200),
    cursor: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> list[AgentDetailResponse]:
    stmt = (
        select(models.Agent)
        .where(models.Agent.account_id == ctx.account_id)
        .order_by(models.Agent.created_at.desc())
    )
    if cursor:
        stmt = stmt.where(models.Agent.id < cursor)
    stmt = stmt.limit(limit)

    rows = db.scalars(stmt)
    result: list[AgentDetailResponse] = []
    for row in rows:
        cert = next((c for c in [row.certificate] if c), None)
        latest = row.genome_versions[-1] if row.genome_versions else None
        if not cert or not latest:
            continue
        result.append(
            AgentDetailResponse(
                agent_id=row.agent_id,
                certificate_id=cert.certificate_id,
                name=row.name,
                creator=row.creator,
                jurisdiction=row.jurisdiction,
                declared_purpose=row.declared_purpose,
                status=row.status,
                genome=GenomePayload(**latest.payload),
                parent_agent_ids=cert.parent_agent_ids,
                created_at=row.created_at,
                certificate_uri=cert.document_uri,
                version_count=len(row.genome_versions),
                latest_genome_hash=latest.genome_hash,
            )
        )
    return result


@router.get("/{agent_id}", response_model=AgentDetailResponse)
def get_agent(
    agent_id: str,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> AgentDetailResponse:
    agent = db.execute(
        select(models.Agent)
        .where(models.Agent.account_id == ctx.account_id, models.Agent.agent_id == agent_id)
    ).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent_id")
    latest = db.execute(
        select(models.GenomeVersion)
        .where(models.GenomeVersion.agent_id == agent.id)
        .order_by(models.GenomeVersion.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    if not latest:
        raise HTTPException(status_code=500, detail="Agent has no genome versions")

    cert = agent.certificate
    if not cert:
        raise HTTPException(status_code=500, detail="Agent certificate missing")

    return AgentDetailResponse(
        agent_id=agent.agent_id,
        certificate_id=cert.certificate_id,
        name=agent.name,
        creator=agent.creator,
        jurisdiction=agent.jurisdiction,
        declared_purpose=agent.declared_purpose,
        status=agent.status,
        genome=GenomePayload(**latest.payload),
        parent_agent_ids=cert.parent_agent_ids,
        created_at=agent.created_at,
        certificate_uri=cert.document_uri,
        version_count=len(agent.genome_versions),
        latest_genome_hash=latest.genome_hash,
    )


@router.get("/{agent_id}/certificate", response_model=CertificateDownloadResponse)
def get_certificate(
    agent_id: str,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> CertificateDownloadResponse:
    agent = db.execute(
        select(models.Agent)
        .where(models.Agent.account_id == ctx.account_id, models.Agent.agent_id == agent_id)
    ).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent_id")
    cert = agent.certificate
    if not cert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate not found")
    return CertificateDownloadResponse(
        certificate_id=cert.certificate_id,
        document_uri=cert.document_uri,
        issued_at=cert.issued_at,
    )


@router.patch("/{agent_id}/genome", response_model=GenomePayload)
def update_genome(
    agent_id: str,
    payload: GenomeUpdateRequest,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> GenomePayload:
    service = GenomeService(db)
    try:
        return service.update_genome(agent_id, payload)
    except ValueError as exc:
        message = str(exc).lower()
        status_code = status.HTTP_404_NOT_FOUND
        if "unknown" in message:
            status_code = status.HTTP_404_NOT_FOUND
        elif "unchanged" in message:
            status_code = status.HTTP_409_CONFLICT
        else:
            status_code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
