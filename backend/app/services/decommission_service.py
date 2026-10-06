"""Decommissioning: the only way an agent leaves service. Nothing is deleted."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import DecommissionRequest, DecommissionResponse, LedgerEventCreate
from .ledger_service import LedgerService
from .principal import principal_label


class AlreadyDecommissioned(ValueError):
    pass


def _count(db: Session, model, agent_db_id: int) -> int:
    return db.execute(
        select(func.count()).select_from(model).where(model.agent_id == agent_db_id)
    ).scalar_one()


class DecommissionService:
    def __init__(self, db: Session):
        self.db = db

    def decommission(
        self,
        agent_id: str,
        payload: DecommissionRequest,
        *,
        account_id: int,
        decommissioned_by: dict[str, Any],
    ) -> DecommissionResponse:
        def mark(locked: models.Agent) -> dict[str, Any]:
            if locked.status == "decommissioned":
                raise AlreadyDecommissioned("Agent is already decommissioned")
            previous_status = locked.status
            locked.status = "decommissioned"
            return {"previous_status": previous_status}

        event = LedgerService(self.db).log_event(
            LedgerEventCreate(
                agent_id=agent_id,
                event_type="decommission",
                actor=principal_label(decommissioned_by),
                summary="Agent decommissioned",
                details={
                    "reason": payload.reason,
                    "decommissioned_by": decommissioned_by,
                    "declared_actor": payload.actor,
                    "records_retained": True,
                },
            ),
            account_id=account_id,
            prepare=mark,
        )
        agent = self.db.execute(
            select(models.Agent).where(
                models.Agent.agent_id == agent_id, models.Agent.account_id == account_id
            )
        ).scalar_one()
        return DecommissionResponse(
            agent_id=agent.agent_id,
            status="decommissioned",
            decommissioned_at=event.created_at,
            reason=payload.reason,
            decommissioned_by=decommissioned_by,
            declared_actor=payload.actor,
            event_id=event.event_id,
            event_hash=event.event_hash,
            retained={
                "ledger_events": _count(self.db, models.LedgerEvent, agent.id),
                "genome_versions": _count(self.db, models.GenomeVersion, agent.id),
                "birth_certificates": _count(self.db, models.BirthCertificate, agent.id),
            },
        )
