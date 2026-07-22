from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..dependencies import get_db, require_role
from ..schemas import (
    CertificateDownloadResponse,
    AgentCreateRequest,
    AgentDetailResponse,
    AgentResponse,
    GenomePayload,
    GenomeUpdateRequest,
    ExecutionValidateRequest,
    ExecutionValidateResponse,
)
from ..services.certificate_service import CertificateService
from ..services.genome_service import GenomeService
from .. import models

router = APIRouter()


@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: AgentCreateRequest,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> AgentResponse:
    service = CertificateService(db)
    try:
        return service.register_agent(payload, account_id=ctx.account_id)
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

        snapshot = row.trust_snapshot
        if snapshot:
            trust_score = snapshot.trust_score
            risk_tier = snapshot.risk_tier
            trust_policy_version = snapshot.trust_policy_version
            evidence_head = snapshot.evidence_head
        else:
            from ..services.trust_policy import TrustPolicyV1
            trust_data = TrustPolicyV1.calculate_trust(row.ledger_events)
            trust_score = trust_data["trust_score"]
            risk_tier = trust_data["risk_tier"]
            trust_policy_version = trust_data["trust_policy_version"]
            evidence_head = trust_data["evidence_head"]

        result.append(
            AgentDetailResponse(
                agent_id=row.agent_id,
                certificate_id=cert.certificate_id,
                name=row.name,
                creator=row.creator,
                jurisdiction=row.jurisdiction,
                declared_purpose=row.declared_purpose,
                status=row.status,
                trust_score=trust_score,
                risk_tier=risk_tier,
                trust_policy_version=trust_policy_version,
                evidence_head=evidence_head,
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

    snapshot = agent.trust_snapshot
    if snapshot:
        trust_score = snapshot.trust_score
        risk_tier = snapshot.risk_tier
        trust_policy_version = snapshot.trust_policy_version
        evidence_head = snapshot.evidence_head
    else:
        from ..services.trust_policy import TrustPolicyV1
        trust_data = TrustPolicyV1.calculate_trust(agent.ledger_events)
        trust_score = trust_data["trust_score"]
        risk_tier = trust_data["risk_tier"]
        trust_policy_version = trust_data["trust_policy_version"]
        evidence_head = trust_data["evidence_head"]

    return AgentDetailResponse(
        agent_id=agent.agent_id,
        certificate_id=cert.certificate_id,
        name=agent.name,
        creator=agent.creator,
        jurisdiction=agent.jurisdiction,
        declared_purpose=agent.declared_purpose,
        status=agent.status,
        trust_score=trust_score,
        risk_tier=risk_tier,
        trust_policy_version=trust_policy_version,
        evidence_head=evidence_head,
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


@router.post("/{agent_id}/trust/rebuild", response_model=AgentDetailResponse)
def rebuild_agent_trust(
    agent_id: str,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> AgentDetailResponse:
    agent = db.execute(
        select(models.Agent)
        .where(models.Agent.account_id == ctx.account_id, models.Agent.agent_id == agent_id)
    ).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent_id")

    from ..services.trust_policy import TrustPolicyV1
    from ..utils import utc_now
    trust_data = TrustPolicyV1.calculate_trust(agent.ledger_events)

    snapshot = agent.trust_snapshot
    if not snapshot:
        snapshot = models.AgentTrustSnapshot(agent_id=agent.id)
        db.add(snapshot)
        agent.trust_snapshot = snapshot

    snapshot.trust_score = trust_data["trust_score"]
    snapshot.risk_tier = trust_data["risk_tier"]
    snapshot.trust_policy_version = trust_data["trust_policy_version"]
    snapshot.evidence_head = trust_data["evidence_head"]
    snapshot.calculated_at = utc_now()

    db.commit()
    db.refresh(agent)

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
        trust_score=snapshot.trust_score,
        risk_tier=snapshot.risk_tier,
        trust_policy_version=snapshot.trust_policy_version,
        evidence_head=snapshot.evidence_head,
        genome=GenomePayload(**latest.payload),
        parent_agent_ids=cert.parent_agent_ids,
        created_at=agent.created_at,
        certificate_uri=cert.document_uri,
        version_count=len(agent.genome_versions),
        latest_genome_hash=latest.genome_hash,
    )


@router.post("/execution/validate", response_model=ExecutionValidateResponse)
def validate_execution(
    payload: ExecutionValidateRequest,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> ExecutionValidateResponse:
    agent = db.execute(
        select(models.Agent)
        .where(models.Agent.agent_id == payload.agent_id)
    ).scalar_one_or_none()
    
    if not agent:
        return ExecutionValidateResponse(
            allowed=False,
            agent_certificate_id=None,
            canonical_genome_hash=None,
            trust_score=0.0,
            risk_tier="terminated",
            trust_policy_version="v1",
            evidence_head=None,
        )

    # Validate active status
    if agent.status not in ("active", "registered", "standard"):
        return ExecutionValidateResponse(
            allowed=False,
            agent_certificate_id=agent.certificate.certificate_id if agent.certificate else None,
            canonical_genome_hash=agent.genome_versions[-1].genome_hash if agent.genome_versions else None,
            trust_score=0.0,
            risk_tier="terminated",
            trust_policy_version="v1",
            evidence_head=None,
        )

    # Validate workspace
    if agent.workspace_id and agent.workspace_id != payload.workspace_id:
        return ExecutionValidateResponse(
            allowed=False,
            agent_certificate_id=agent.certificate.certificate_id if agent.certificate else None,
            canonical_genome_hash=agent.genome_versions[-1].genome_hash if agent.genome_versions else None,
            trust_score=0.0,
            risk_tier="terminated",
            trust_policy_version="v1",
            evidence_head=None,
        )
    
    if not agent.workspace_id:
        agent.workspace_id = payload.workspace_id
        db.commit()

    latest_version = agent.genome_versions[-1] if agent.genome_versions else None
    if not latest_version or latest_version.genome_hash != payload.expected_genome_hash:
        return ExecutionValidateResponse(
            allowed=False,
            agent_certificate_id=agent.certificate.certificate_id if agent.certificate else None,
            canonical_genome_hash=latest_version.genome_hash if latest_version else None,
            trust_score=0.0,
            risk_tier="terminated",
            trust_policy_version="v1",
            evidence_head=None,
        )

    allowed_tools = latest_version.payload.get("tools", [])
    for tool in payload.requested_tools:
        if tool not in allowed_tools:
            return ExecutionValidateResponse(
                allowed=False,
                agent_certificate_id=agent.certificate.certificate_id if agent.certificate else None,
                canonical_genome_hash=latest_version.genome_hash,
                trust_score=0.0,
                risk_tier="terminated",
                trust_policy_version="v1",
                evidence_head=None,
            )

    snapshot = agent.trust_snapshot
    if snapshot:
        trust_score = snapshot.trust_score
        risk_tier = snapshot.risk_tier
        trust_policy_version = snapshot.trust_policy_version
        evidence_head = snapshot.evidence_head
    else:
        from ..services.trust_policy import TrustPolicyV1
        trust_data = TrustPolicyV1.calculate_trust(agent.ledger_events)
        trust_score = trust_data["trust_score"]
        risk_tier = trust_data["risk_tier"]
        trust_policy_version = trust_data["trust_policy_version"]
        evidence_head = trust_data["evidence_head"]

    if risk_tier == "terminated":
        return ExecutionValidateResponse(
            allowed=False,
            agent_certificate_id=agent.certificate.certificate_id if agent.certificate else None,
            canonical_genome_hash=latest_version.genome_hash,
            trust_score=trust_score,
            risk_tier=risk_tier,
            trust_policy_version=trust_policy_version,
            evidence_head=evidence_head,
        )

    return ExecutionValidateResponse(
        allowed=True,
        agent_certificate_id=agent.certificate.certificate_id if agent.certificate else None,
        canonical_genome_hash=latest_version.genome_hash,
        trust_score=trust_score,
        risk_tier=risk_tier,
        trust_policy_version=trust_policy_version,
        evidence_head=evidence_head,
    )
