from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import (
    AdapterUsageLimitResponse,
    AgentDetailResponse,
    CertificateDownloadResponse,
    GenomePayload,
    LedgerChainVerifyRequest,
    LedgerEventResponse,
    VeklmAdapterSnapshot,
)
from ..utils import stable_hash, utc_now
from .billing_service import BillingService
from .ledger_service import LedgerService
from .lineage_service import LineageService


class AdapterService:
    def __init__(self, db: Session):
        self.db = db
        self.billing_service = BillingService(db)
        self.ledger_service = LedgerService(db)
        self.lineage_service = LineageService(db)

    def _get_agent(self, account_id: int, agent_id: str) -> models.Agent:
        agent = self.db.execute(
            select(models.Agent).where(
                models.Agent.account_id == account_id,
                models.Agent.agent_id == agent_id,
            )
        ).scalar_one_or_none()
        if not agent:
            raise ValueError("Unknown agent_id")
        return agent

    def _get_latest_genome(self, agent_db_id: int) -> models.GenomeVersion:
        latest = self.db.execute(
            select(models.GenomeVersion)
            .where(models.GenomeVersion.agent_id == agent_db_id)
            .order_by(models.GenomeVersion.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest is None:
            raise ValueError("Agent has no genome versions")
        return latest

    def get_vekml_snapshot(self, account_id: int, agent_id: str) -> VeklmAdapterSnapshot:
        agent = self._get_agent(account_id, agent_id)
        latest = self._get_latest_genome(agent.id)
        certificate = agent.certificate
        if certificate is None:
            raise ValueError("Certificate not found")

        # Calculate trust score
        base_score = 50.0
        events = agent.ledger_events
        evidence_head = events[-1].event_hash if events else None
        
        for event in events:
            if event.event_type == "birth_registration":
                base_score = max(base_score, 50.0)
            elif event.event_type == "deployment":
                base_score += 10.0
            elif event.event_type == "test_audit":
                base_score += event.details.get("score", 0) / 10.0
            elif event.event_type == "violation":
                base_score -= 20.0
                
        base_score = max(0.0, min(100.0, base_score))
        
        if base_score >= 90:
            risk_tier = "production"
        elif base_score >= 70:
            risk_tier = "standard"
        elif base_score >= 40:
            risk_tier = "sandbox"
        else:
            risk_tier = "terminated"

        agent_detail = AgentDetailResponse(
            agent_id=agent.agent_id,
            certificate_id=certificate.certificate_id,
            name=agent.name,
            creator=agent.creator,
            jurisdiction=agent.jurisdiction,
            declared_purpose=agent.declared_purpose,
            status=agent.status,
            trust_score=base_score,
            risk_tier=risk_tier,
            evidence_head=evidence_head,
            genome=GenomePayload(**latest.payload),
            parent_agent_ids=certificate.parent_agent_ids,
            created_at=agent.created_at,
            certificate_uri=certificate.document_uri,
            version_count=len(agent.genome_versions),
            latest_genome_hash=latest.genome_hash,
        )

        certificate_detail = CertificateDownloadResponse(
            certificate_id=certificate.certificate_id,
            document_uri=certificate.document_uri,
            issued_at=certificate.issued_at,
        )

        ledger_events = self.ledger_service.get_agent_history(agent_id=agent.agent_id, limit=500)
        _, verify_payload = self.ledger_service.verify_chain(agent.agent_id)
        chain_verification = LedgerChainVerifyRequest(**verify_payload)
        lineage = self.lineage_service.get_tree(account_id=account_id, agent_id=agent.agent_id, count_usage=False)

        account = self.db.get(models.Account, account_id)
        if account is None:
            raise ValueError("Unknown account")

        usage_limits: list[AdapterUsageLimitResponse] = []
        for metric in ("certificate_issuance", "lineage_render"):
            used = self.billing_service.get_current_metric(account_id, metric)
            limit = self.billing_service.plan_limit(account, metric)
            usage_limits.append(
                AdapterUsageLimitResponse(
                    metric=metric,
                    used=used,
                    limit=limit,
                    remaining=max(0.0, limit - used),
                )
            )

        exported_at = utc_now()
        snapshot_hash = stable_hash(
            {
                "adapter": "vekml",
                "account_id": account_id,
                "agent_id": agent.agent_id,
                "certificate_id": certificate.certificate_id,
                "latest_genome_hash": latest.genome_hash,
                "latest_event_hash": chain_verification.latest_event_hash,
                "checked_events": chain_verification.checked_events,
                "usage_limits": [row.model_dump() for row in usage_limits],
                "exported_at": exported_at.isoformat(),
            }
        )

        return VeklmAdapterSnapshot(
            adapter="vekml",
            exported_at=exported_at,
            account_id=account_id,
            agent=agent_detail,
            certificate=certificate_detail,
            ledger_events=ledger_events,
            chain_verification=chain_verification,
            lineage=lineage,
            usage_limits=usage_limits,
            snapshot_hash=snapshot_hash,
        )
