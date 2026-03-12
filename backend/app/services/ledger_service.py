from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import LedgerEventCreate, LedgerEventResponse
from ..utils import short_id, stable_hash, utc_now
from .analytics_service import AnalyticsService


class LedgerService:
    def __init__(self, db: Session):
        self.db = db
        self.analytics_service = AnalyticsService(db)

    def _latest_event_hash(self, agent_db_id: int) -> str | None:
        stmt = (
            select(models.LedgerEvent.event_hash)
            .where(models.LedgerEvent.agent_id == agent_db_id)
            .order_by(models.LedgerEvent.id.desc())
            .limit(1)
        )
        result = self.db.execute(stmt).scalar_one_or_none()
        return result

    def log_event(self, payload: LedgerEventCreate) -> LedgerEventResponse:
        agent = self.db.execute(
            select(models.Agent).where(models.Agent.agent_id == payload.agent_id)
        ).scalar_one_or_none()
        if not agent:
            raise ValueError("Unknown agent_id")

        prev_hash = self._latest_event_hash(agent.id)
        event = models.LedgerEvent(
            agent_id=agent.id,
            event_id=short_id("evt"),
            event_type=payload.event_type,
            actor=payload.actor,
            summary=payload.summary,
            details=payload.details,
            prev_event_hash=prev_hash,
            created_at=utc_now(),
            event_hash="",
        )
        event.event_hash = stable_hash(
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "agent_id": agent.agent_id,
                "actor": event.actor,
                "summary": event.summary,
                "details": event.details,
                "prev_event_hash": event.prev_event_hash,
                "created_at": event.created_at.isoformat(),
            }
        )

        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

        self.analytics_service.track(
            event_type=f"ledger_{event.event_type}",
            account_id=agent.account_id,
            payload={
                "agent_id": agent.agent_id,
                "event_id": event.event_id,
                "event_type": event.event_type,
            },
        )

        return LedgerEventResponse(
            event_id=event.event_id,
            event_type=event.event_type,
            actor=event.actor,
            summary=event.summary,
            details=event.details,
            prev_event_hash=event.prev_event_hash,
            event_hash=event.event_hash,
            created_at=event.created_at,
        )

    def get_agent_history(self, agent_id: str) -> list[LedgerEventResponse]:
        agent = self.db.execute(
            select(models.Agent).where(models.Agent.agent_id == agent_id)
        ).scalar_one_or_none()
        if not agent:
            raise ValueError("Unknown agent_id")

        stmt = (
            select(models.LedgerEvent)
            .where(models.LedgerEvent.agent_id == agent.id)
            .order_by(models.LedgerEvent.created_at.asc())
        )
        events: Iterable[models.LedgerEvent] = self.db.scalars(stmt)
        return [
            LedgerEventResponse(
                event_id=e.event_id,
                event_type=e.event_type,
                actor=e.actor,
                summary=e.summary,
                details=e.details,
                prev_event_hash=e.prev_event_hash,
                event_hash=e.event_hash,
                created_at=e.created_at,
            )
            for e in events
        ]
