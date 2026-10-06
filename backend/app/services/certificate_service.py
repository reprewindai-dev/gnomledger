from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from ..schemas import (
    AgentCreateRequest,
    AgentResponse,
    CertificateDownloadResponse,
    GenomePayload,
    LOG_RETENTION_REASON,
    missing_accountability_fields,
    missing_integrity_fields,
)
from ..utils import canonical_timestamp, short_id, stable_hash, utc_now
from .analytics_service import AnalyticsService
from .agent_handle import allocate_handle
from .billing_service import BillingService
from .principal import principal_label
from .signing_service import CANONICALIZATION, ISSUER, get_signer

_settings = get_settings()

CERTIFICATE_SCHEMA_VERSION = "pgl.birth_certificate.v2"

AUTHORITY_STATEMENT = (
    "capability_refs name CAPPO capability packages; CAPPO is the enforcement authority and "
    "mounts only these. permissions and safety_rules are declarations recorded for audit and "
    "are not enforced. tools are checked only when a runtime calls "
    "POST /api/v1/agents/execution/validate."
)
MODEL_STATEMENT = (
    "This certificate identifies a kind of agent, registered once. Each task is a separate "
    "ephemeral execution that cites this genome; the model a task actually used is recorded "
    "on that task's execution evidence as model_used and must be one of declared_models."
)
RETENTION_STATEMENT = (
    "This ledger does not delete ledger events, genome versions or certificates, including "
    "after decommissioning. log_retention_days is the declared minimum retention."
)


def build_certificate_document(
    *,
    agent: models.Agent,
    certificate_id: str,
    genome: GenomePayload,
    genome_hash: str,
    genome_version: int,
    parent_agent_ids: list[str],
    issued_at: datetime,
    key_id: str,
    agent_handle: str | None = None,
    registered_by: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The signed birth certificate. Every value is JSON-native so it round-trips through
    the database unchanged and re-serializes to the exact signed bytes.

    The accountable party is the operator (registered_by, accountable_owner), never the
    agent: the agent is a generic, disposable executor named by its handle."""
    owner = genome.accountable_owner.model_dump() if genome.accountable_owner else None
    oversight = genome.oversight.model_dump() if genome.oversight else None
    return {
        "schema_version": CERTIFICATE_SCHEMA_VERSION,
        "version": 1,
        "issuer": ISSUER,
        "key_id": key_id,
        "canonicalization": CANONICALIZATION,
        "certificate_id": certificate_id,
        "agent_id": agent.agent_id,
        "agent_handle": agent_handle,
        "name": agent.name,
        "creator": agent.creator,
        "jurisdiction": agent.jurisdiction,
        "declared_purpose": agent.declared_purpose,
        "issued_at": issued_at.isoformat(),
        "parent_agent_ids": list(parent_agent_ids),
        "genome_hash": genome_hash,
        "genome_version": genome_version,
        "genome_hash_method": "sha256 of the pgl-c14n bytes of the canonical genome",
        "model": {
            "declared_models": genome.effective_models(),
            "declared_models_source": (
                "declared_models" if genome.declared_models else "single_model_fields"
            ),
            "model_family": genome.model_family,
            "model_version": genome.model_version,
            "architecture": genome.architecture,
            "model_provider": genome.model_provider,
            "model_identifier": genome.model_identifier,
            "statement": MODEL_STATEMENT,
        },
        "accountability": {
            # The authenticated operator that registered the agent (from the API key).
            "registered_by": registered_by,
            "accountable_owner": owner,
            "incident_contact": genome.incident_contact,
            "deployer": genome.deployer,
            "provider": genome.provider,
        },
        "run_mode": {
            "mode": genome.run_mode,
            "authorized_by": registered_by if genome.run_mode else None,
            "authorized_at": issued_at.isoformat() if genome.run_mode else None,
        },
        "context": {
            "industry": genome.industry,
            "intended_use": genome.intended_use,
            "jurisdiction": agent.jurisdiction,
        },
        "bounded_use": {
            "intended_use": genome.intended_use,
            "out_of_scope_uses": list(genome.out_of_scope_uses),
            "known_limitations": list(genome.known_limitations),
            "data_categories": list(genome.data_categories),
            "risk_category": genome.risk_category,
            "regulatory_risk_class": genome.regulatory_risk_class,
            "risk_rationale": genome.risk_rationale,
        },
        "oversight": oversight,
        "authority": {
            "capability_refs": list(genome.capability_refs),
            "capability_enforcement": "CAPPO",
            "declared_permissions": list(genome.permissions),
            "permissions_enforcement": "declarative",
            "declared_safety_rules": list(genome.safety_rules),
            "declared_tools": list(genome.tools),
            "statement": AUTHORITY_STATEMENT,
        },
        "configuration_integrity": {
            "system_prompt_sha256": genome.system_prompt_sha256,
            "code_commit": genome.code_commit,
            "image_digest": genome.image_digest,
            "tool_versions": dict(genome.tool_versions),
        },
        "retention": {
            "log_retention_days": genome.log_retention_days,
            "basis": LOG_RETENTION_REASON.split(". ", 1)[1],
            "statement": RETENTION_STATEMENT,
        },
        "missing_accountability_fields": missing_accountability_fields(genome),
        "missing_integrity_fields": missing_integrity_fields(genome),
    }


def sign_certificate(
    db: Session, certificate: models.BirthCertificate, document: dict[str, Any]
) -> models.CertificateSignature:
    block = get_signer().sign(document)
    row = models.CertificateSignature(
        birth_certificate_id=certificate.id,
        algorithm=block["algorithm"],
        key_id=block["key_id"],
        signature=block["value"],
        signed_at=utc_now(),
    )
    certificate.certificate_payload = document
    certificate.signature = row
    db.add(row)
    return row


def write_certificate_artifact(certificate: models.BirthCertificate) -> str:
    """Store the signed envelope next to the database so it can be handed out as a file."""
    doc_path = Path(_settings.certificate_storage_path)
    doc_path.mkdir(parents=True, exist_ok=True)
    artifact_path = doc_path / f"{certificate.certificate_id}.json"
    envelope = {
        "certificate": certificate.certificate_payload,
        "signature": certificate.signature.block() if certificate.signature else None,
    }
    with open(artifact_path, "w", encoding="utf-8") as fp:
        json.dump(envelope, fp, sort_keys=True)
    return str(artifact_path)


def certificate_view(db: Session, certificate: models.BirthCertificate) -> CertificateDownloadResponse:
    current_hash = db.execute(
        select(models.GenomeVersion.genome_hash)
        .where(models.GenomeVersion.agent_id == certificate.agent_id)
        .order_by(models.GenomeVersion.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    signature = certificate.signature
    document = certificate.certificate_payload
    if signature is not None and document is not None:
        return CertificateDownloadResponse(
            certificate_id=certificate.certificate_id,
            document_uri=certificate.document_uri,
            issued_at=certificate.issued_at,
            signature_status="signed",
            certificate=document,
            signature=signature.block(),
            key_id=signature.key_id,
            missing_accountability_fields=document.get("missing_accountability_fields", []),
            missing_integrity_fields=document.get("missing_integrity_fields", []),
            current_genome_hash=current_hash,
        )
    # Issued before signing: report gaps from the birth genome so silence is not mistaken
    # for completeness.
    birth = db.execute(
        select(models.GenomeVersion.payload)
        .where(models.GenomeVersion.agent_id == certificate.agent_id)
        .order_by(models.GenomeVersion.version.asc())
        .limit(1)
    ).scalar_one_or_none()
    birth_genome = GenomePayload(**birth) if birth else None
    return CertificateDownloadResponse(
        certificate_id=certificate.certificate_id,
        document_uri=certificate.document_uri,
        issued_at=certificate.issued_at,
        signature_status="unsigned_legacy",
        certificate=document,
        missing_accountability_fields=(
            missing_accountability_fields(birth_genome) if birth_genome else []
        ),
        missing_integrity_fields=missing_integrity_fields(birth_genome) if birth_genome else [],
        current_genome_hash=current_hash,
    )


class CertificateService:
    def __init__(self, db: Session):
        self.db = db
        self.billing_service = BillingService(db)
        self.analytics_service = AnalyticsService(db)

    def _get_account(self, account_id: int) -> models.Account:
        account = self.db.execute(select(models.Account).where(models.Account.id == account_id)).scalar_one_or_none()
        if not account:
            raise ValueError("Unknown account")
        if account.status != "active":
            raise ValueError("Account is not active")
        return account

    def _assert_parent_agents_exist(self, account_id: int, parent_ids: list[str]) -> list[models.Agent]:
        if not parent_ids:
            return []
        stmt = (
            select(models.Agent)
            .where(models.Agent.account_id == account_id, models.Agent.agent_id.in_(parent_ids))
            .order_by(models.Agent.id.asc())
        )
        rows = list(self.db.scalars(stmt))
        if len(rows) != len(set(parent_ids)):
            raise ValueError("One or more parent_agent_ids do not exist for this account")
        return rows

    def register_agent(
        self,
        payload: AgentCreateRequest,
        account_id: int,
        registered_by: dict[str, Any] | None = None,
    ) -> AgentResponse:
        account = self._get_account(account_id)
        self._assert_parent_agents_exist(account_id, payload.parent_agent_ids)

        limit = self.billing_service.plan_limit(account, "certificate_issuance")
        self.billing_service.ensure_or_raise(account.id, "certificate_issuance", limit)

        agent_identifier = short_id("agent")
        certificate_identifier = short_id("cert")
        # First write of the registration: a lost race for the sequence number rolls back
        # and retries before anything else has been written.
        handle = allocate_handle(self.db, account, agent_identifier).handle
        parent_agents = self._assert_parent_agents_exist(account_id, payload.parent_agent_ids)
        now = utc_now()
        agent_name = payload.agent_name or handle
        creator = payload.creator or principal_label(registered_by)

        agent = models.Agent(
            account_id=account.id,
            agent_id=agent_identifier,
            name=agent_name,
            creator=creator,
            jurisdiction=payload.jurisdiction,
            declared_purpose=payload.genome.intended_use,
        )
        self.db.add(agent)
        self.db.flush()

        genome_canonical = payload.genome.canonical()
        genome_hash = stable_hash(genome_canonical)
        genome_version = models.GenomeVersion(
            agent_id=agent.id,
            version=1,
            payload=genome_canonical,
            genome_hash=genome_hash,
            note="Initial registration",
            created_at=now,
        )

        certificate_payload = build_certificate_document(
            agent=agent,
            certificate_id=certificate_identifier,
            genome=payload.genome,
            genome_hash=genome_hash,
            genome_version=1,
            parent_agent_ids=payload.parent_agent_ids,
            issued_at=now,
            key_id=get_signer().key_id,
            agent_handle=handle,
            registered_by=registered_by,
        )

        certificate = models.BirthCertificate(
            agent_id=agent.id,
            certificate_id=certificate_identifier,
            genome_hash=genome_hash,
            parent_agent_ids=payload.parent_agent_ids,
            issued_at=now,
        )

        self.db.add_all([genome_version, certificate])
        self.db.flush()
        sign_certificate(self.db, certificate, certificate_payload)
        for parent in parent_agents:
            self.db.add(
                models.LineageEdge(
                    parent_agent_id=parent.id,
                    child_agent_id=agent.id,
                )
            )

        ledger_event = models.LedgerEvent(
            agent_id=agent.id,
            event_id=short_id("evt"),
            event_type="birth_registration",
            actor=creator,
            summary=f"Registered agent '{agent_name}'"[:255],
            details={
                "certificate_id": certificate_identifier,
                "jurisdiction": payload.jurisdiction,
                "parent_agent_ids": payload.parent_agent_ids,
                "agent_handle": handle,
                "registered_by": registered_by,
                "run_mode_authorization": certificate_payload["run_mode"],
            },
            prev_event_hash=None,
            event_hash="",
        )
        ledger_event.created_at = utc_now()
        ledger_event.event_hash = stable_hash(
            {
                "event_id": ledger_event.event_id,
                "event_type": ledger_event.event_type,
                "agent_id": agent.agent_id,
                "actor": ledger_event.actor,
                "summary": ledger_event.summary,
                "details": ledger_event.details,
                "prev_event_hash": ledger_event.prev_event_hash,
                "created_at": canonical_timestamp(ledger_event.created_at),
            }
        )
        self.db.add(ledger_event)
        self.db.flush()
        self.billing_service.record_usage(account.id, "certificate_issuance", 1.0)

        # Recalculate trust snapshot and save to DB in same transaction
        from .trust_policy import TrustPolicyV1
        trust_data = TrustPolicyV1.calculate_trust([ledger_event])

        snapshot = models.AgentTrustSnapshot(
            agent_id=agent.id,
            trust_score=trust_data["trust_score"],
            risk_tier=trust_data["risk_tier"],
            trust_policy_version=trust_data["trust_policy_version"],
            evidence_head=trust_data["evidence_head"],
            calculated_at=utc_now()
        )
        self.db.add(snapshot)
        agent.trust_snapshot = snapshot

        self.db.commit()
        self.db.refresh(agent)
        self.db.refresh(certificate)

        # Store a verifiable certificate artifact.
        certificate.document_uri = write_certificate_artifact(certificate)
        self.db.commit()

        self.analytics_service.track(
            event_type="certificate_issued",
            account_id=account.id,
            payload={
                "agent_id": agent.agent_id,
                "certificate_id": certificate_identifier,
                "tier": account.tier,
            },
        )

        return AgentResponse(
            agent_id=agent.agent_id,
            certificate_id=certificate_identifier,
            name=agent.name,
            creator=agent.creator,
            jurisdiction=agent.jurisdiction,
            declared_purpose=agent.declared_purpose,
            status=agent.status,
            trust_score=snapshot.trust_score,
            risk_tier=snapshot.risk_tier,
            trust_policy_version=snapshot.trust_policy_version,
            evidence_head=snapshot.evidence_head,
            genome=payload.genome,
            parent_agent_ids=payload.parent_agent_ids,
            created_at=agent.created_at,
            certificate=certificate_view(self.db, certificate),
            agent_handle=handle,
        )
