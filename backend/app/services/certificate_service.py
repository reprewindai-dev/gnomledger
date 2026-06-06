from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from ..schemas import AgentCreateRequest, AgentResponse
from ..utils import canonical_timestamp, short_id, stable_hash, utc_now
from .analytics_service import AnalyticsService
from .billing_service import BillingService

_settings = get_settings()

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
    ) -> AgentResponse:
        account = self._get_account(account_id)
        parent_agents = self._assert_parent_agents_exist(account_id, payload.parent_agent_ids)

        limit = self.billing_service.plan_limit(account, "certificate_issuance")
        self.billing_service.ensure_or_raise(account.id, "certificate_issuance", limit)

        agent_identifier = short_id("agent")
        certificate_identifier = short_id("cert")
        now = utc_now()

        agent = models.Agent(
            account_id=account.id,
            agent_id=agent_identifier,
            name=payload.agent_name,
            creator=payload.creator,
            jurisdiction=payload.jurisdiction,
            declared_purpose=payload.genome.intended_use,
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

        certificate_payload = {
            "version": 1,
            "agent_id": agent.agent_id,
            "certificate_id": certificate_identifier,
            "name": agent.name,
            "creator": agent.creator,
            "jurisdiction": agent.jurisdiction,
            "declared_purpose": agent.declared_purpose,
            "genome_hash": genome_hash,
            "issued_at": now.isoformat(),
        }

        certificate = models.BirthCertificate(
            agent_id=agent.id,
            certificate_id=certificate_identifier,
            genome_hash=genome_hash,
            parent_agent_ids=payload.parent_agent_ids,
            issued_at=now,
            certificate_payload=certificate_payload,
        )

        self.db.add_all([genome_version, certificate])
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

        self.db.commit()
        self.db.refresh(agent)
        self.db.refresh(certificate)

        # Store a verifiable certificate artifact.
        doc_path = Path(_settings.certificate_storage_path)
        doc_path.mkdir(parents=True, exist_ok=True)
        artifact_path = doc_path / f"{certificate_identifier}.json"
        with open(artifact_path, "w", encoding="utf-8") as fp:
            json.dump(certificate_payload, fp)
        certificate.document_uri = str(artifact_path)
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
            genome=payload.genome,
            parent_agent_ids=payload.parent_agent_ids,
            created_at=agent.created_at,
        )
