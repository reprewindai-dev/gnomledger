from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .. import models
from ..schemas import AgentCreateRequest, AgentResponse
from ..utils import short_id, stable_hash, utc_now
from .analytics_service import AnalyticsService
from .billing_service import BillingService

TIER_CERTIFICATE_LIMIT = {
    "launch": 25,
    "scale": 250,
    "enterprise": 1000,
}


class CertificateService:
    def __init__(self, db: Session):
        self.db = db
        self.billing_service = BillingService(db)
        self.analytics_service = AnalyticsService(db)

    def _get_account(self, account_id: int) -> models.Account:
        account = self.db.get(models.Account, account_id)
        if not account:
            raise ValueError("Unknown account")
        return account

    def register_agent(self, payload: AgentCreateRequest) -> AgentResponse:
        account = self._get_account(payload.account_id)
        limit = TIER_CERTIFICATE_LIMIT.get(account.tier, 25)
        if not self.billing_service.ensure_quota(account.id, "certificate_issuance", limit):
            raise ValueError("Certificate quota exceeded. Upgrade plan to continue issuing agents.")

        agent_identifier = short_id("agent")
        certificate_identifier = short_id("cert")
        now = utc_now()

        agent = models.Agent(
            account_id=payload.account_id,
            agent_id=agent_identifier,
            name=payload.agent_name,
            creator=payload.creator,
            jurisdiction=payload.jurisdiction,
            declared_purpose=payload.genome.intended_use,
            created_at=now,
        )
        self.db.add(agent)
        self.db.flush()

        genome_hash = stable_hash(payload.genome.model_dump())
        genome_version = models.GenomeVersion(
            agent_id=agent.id,
            version=1,
            payload=payload.genome.model_dump(),
            genome_hash=genome_hash,
            note="Initial registration",
            created_at=now,
        )
        certificate = models.BirthCertificate(
            agent_id=agent.id,
            certificate_id=certificate_identifier,
            genome_hash=genome_hash,
            parent_agent_ids=payload.parent_agent_ids,
            issued_at=datetime.utcnow(),
        )

        self.db.add_all([genome_version, certificate])

        ledger_event = models.LedgerEvent(
            agent_id=agent.id,
            event_id=short_id("evt"),
            event_type="birth_registration",
            actor=payload.creator,
            summary=f"Registered agent '{payload.agent_name}'",
            details={
                "certificate_id": certificate_identifier,
                "jurisdiction": payload.jurisdiction,
                "parent_agent_ids": payload.parent_agent_ids,
            },
            prev_event_hash=None,
            event_hash="",
        )
        ledger_event.event_hash = stable_hash(
            {
                "event_id": ledger_event.event_id,
                "event_type": ledger_event.event_type,
                "agent_id": agent.agent_id,
                "actor": ledger_event.actor,
                "summary": ledger_event.summary,
                "details": ledger_event.details,
                "prev_event_hash": ledger_event.prev_event_hash,
            }
        )
        self.db.add(ledger_event)

        self.db.commit()
        self.db.refresh(agent)

        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.billing_service.record_usage(
            account_id=account.id,
            metric="certificate_issuance",
            amount=1,
            period_start=period_start,
            period_end=now,
        )

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
            genome=payload.genome,
            parent_agent_ids=payload.parent_agent_ids,
            created_at=agent.created_at,
        )
