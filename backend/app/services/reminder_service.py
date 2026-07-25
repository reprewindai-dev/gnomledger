from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import AuditReminderCreate, AuditReminderResponse
from ..utils import short_id, utc_now


def _to_response(reminder: models.AuditReminder, agent_public_id: str) -> AuditReminderResponse:
    return AuditReminderResponse(
        reminder_id=reminder.reminder_id,
        agent_id=agent_public_id,
        title=reminder.title,
        message=reminder.message,
        frequency=reminder.frequency,
        next_trigger_at=reminder.next_trigger_at,
        last_triggered_at=reminder.last_triggered_at,
        is_active=reminder.is_active,
        created_at=reminder.created_at,
    )


class ReminderService:
    def __init__(self, db: Session):
        self.db = db

    def _get_agent(self, account_id: int | None, agent_id: str) -> models.Agent:
        conditions = [models.Agent.agent_id == agent_id]
        if account_id is not None:
            conditions.append(models.Agent.account_id == account_id)
        agent = self.db.execute(select(models.Agent).where(*conditions)).scalar_one_or_none()
        if not agent:
            raise ValueError("Unknown agent_id")
        return agent

    def create_reminder(self, payload: AuditReminderCreate, account_id: int | None = None) -> AuditReminderResponse:
        agent = self._get_agent(account_id, payload.agent_id)
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

    def list_reminders(
        self,
        account_id: int | None = None,
        agent_id: str | None = None,
        active_only: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[AuditReminderResponse]:
        stmt = (
            select(models.AuditReminder, models.Agent)
            .join(models.Agent, models.AuditReminder.agent_id == models.Agent.id)
            .order_by(models.AuditReminder.next_trigger_at.asc())
            .offset(offset)
            .limit(limit)
        )
        if account_id is not None:
            stmt = stmt.where(models.Agent.account_id == account_id)
        if agent_id:
            stmt = stmt.where(models.Agent.agent_id == agent_id)
        if active_only:
            stmt = stmt.where(models.AuditReminder.is_active.is_(True))
        rows = self.db.execute(stmt).all()
        return [_to_response(reminder, agent.agent_id) for reminder, agent in rows]

    def get_reminder(self, reminder_id: str, agent_id: str | None = None, account_id: int | None = None) -> AuditReminderResponse:
        stmt = (
            select(models.AuditReminder, models.Agent)
            .join(models.Agent, models.AuditReminder.agent_id == models.Agent.id)
            .where(models.AuditReminder.reminder_id == reminder_id)
        )
        if account_id is not None:
            stmt = stmt.where(models.Agent.account_id == account_id)
        if agent_id:
            stmt = stmt.where(models.Agent.agent_id == agent_id)
        row = self.db.execute(stmt).one_or_none()
        if not row:
            raise ValueError("Unknown reminder_id")
        reminder, agent = row
        return _to_response(reminder, agent.agent_id)

    def update_reminder(
        self,
        reminder_id: str,
        *,
        title: str | None = None,
        message: str | None = None,
        frequency: str | None = None,
        next_trigger_at: datetime | None = None,
        is_active: bool | None = None,
        agent_id: str | None = None,
        account_id: int | None = None,
    ) -> AuditReminderResponse:
        stmt = (
            select(models.AuditReminder, models.Agent)
            .join(models.Agent, models.AuditReminder.agent_id == models.Agent.id)
            .where(models.AuditReminder.reminder_id == reminder_id)
        )
        if account_id is not None:
            stmt = stmt.where(models.Agent.account_id == account_id)
        if agent_id:
            stmt = stmt.where(models.Agent.agent_id == agent_id)
        row = self.db.execute(stmt).one_or_none()
        if not row:
            raise ValueError("Unknown reminder_id")
        reminder, agent = row
        if title is not None:
            reminder.title = title
        if message is not None:
            reminder.message = message
        if frequency is not None:
            reminder.frequency = frequency
        if next_trigger_at is not None:
            reminder.next_trigger_at = next_trigger_at
        if is_active is not None:
            reminder.is_active = is_active
        self.db.commit()
        self.db.refresh(reminder)
        return _to_response(reminder, agent.agent_id)

    def delete_reminder(self, reminder_id: str, agent_id: str | None = None, account_id: int | None = None) -> None:
        stmt = select(models.AuditReminder).join(models.Agent).where(
            models.AuditReminder.reminder_id == reminder_id
        )
        if account_id is not None:
            stmt = stmt.where(models.Agent.account_id == account_id)
        if agent_id:
            stmt = stmt.where(models.Agent.agent_id == agent_id)
        reminder = self.db.execute(stmt).scalar_one_or_none()
        if not reminder:
            raise ValueError("Unknown reminder_id")
        self.db.delete(reminder)
        self.db.commit()

    def trigger_reminder(self, reminder_id: str, agent_id: str | None = None, account_id: int | None = None) -> AuditReminderResponse:
        stmt = (
            select(models.AuditReminder, models.Agent)
            .join(models.Agent, models.AuditReminder.agent_id == models.Agent.id)
            .where(models.AuditReminder.reminder_id == reminder_id)
        )
        if account_id is not None:
            stmt = stmt.where(models.Agent.account_id == account_id)
        if agent_id:
            stmt = stmt.where(models.Agent.agent_id == agent_id)
        row = self.db.execute(stmt).one_or_none()
        if not row:
            raise ValueError("Unknown reminder_id")
        reminder, agent = row
        now = utc_now()
        reminder.last_triggered_at = now
        delta = {
            "daily": timedelta(days=1),
            "weekly": timedelta(weeks=1),
            "monthly": timedelta(days=30),
        }.get(reminder.frequency)
        if delta:
            reminder.next_trigger_at = now + delta
        else:
            reminder.is_active = False
        self.db.commit()
        self.db.refresh(reminder)
        return _to_response(reminder, agent.agent_id)
