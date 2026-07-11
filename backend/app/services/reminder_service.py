from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import AuditReminderCreate, AuditReminderResponse
from ..utils import short_id, utc_now


def _to_response(rem: models.AuditReminder, agent_public_id: str) -> AuditReminderResponse:
    return AuditReminderResponse(
        reminder_id=rem.reminder_id,
        agent_id=agent_public_id,
        title=rem.title,
        message=rem.message,
        frequency=rem.frequency,
        next_trigger_at=rem.next_trigger_at,
        last_triggered_at=rem.last_triggered_at,
        is_active=rem.is_active,
        created_at=rem.created_at,
    )


class ReminderService:
    def __init__(self, db: Session):
        self.db = db

    def _get_agent(self, agent_id: str) -> models.Agent:
        agent = self.db.execute(
            select(models.Agent).where(models.Agent.agent_id == agent_id)
        ).scalar_one_or_none()
        if not agent:
            raise ValueError("Unknown agent_id")
        return agent

    def create_reminder(self, payload: AuditReminderCreate) -> AuditReminderResponse:
        agent = self._get_agent(payload.agent_id)

        reminder = models.AuditReminder(
            agent_id=agent.id,
            reminder_id=short_id("rem"),
            title=payload.title,
            message=payload.message,
            frequency=payload.frequency,
            next_trigger_at=payload.next_trigger_at,
            is_active=True,
            created_at=utc_now(),
        )
        self.db.add(reminder)
        self.db.commit()
        self.db.refresh(reminder)
        return _to_response(reminder, agent.agent_id)

    def list_reminders(self, agent_id: str | None = None, active_only: bool = False) -> list[AuditReminderResponse]:
        stmt = select(models.AuditReminder, models.Agent).join(models.Agent, models.AuditReminder.agent_id == models.Agent.id)
        if agent_id:
            stmt = stmt.where(models.Agent.agent_id == agent_id)
        if active_only:
            stmt = stmt.where(models.AuditReminder.is_active.is_(True))
        stmt = stmt.order_by(models.AuditReminder.next_trigger_at.asc())

        rows = self.db.execute(stmt).all()
        return [_to_response(rem, agent.agent_id) for rem, agent in rows]

    def delete_reminder(self, reminder_id: str) -> None:
        row = self.db.execute(
            select(models.AuditReminder).where(models.AuditReminder.reminder_id == reminder_id)
        ).scalar_one_or_none()
        if not row:
            raise ValueError("Unknown reminder_id")
        self.db.delete(row)
        self.db.commit()
