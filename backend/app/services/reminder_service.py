from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import Agent, AuditReminder
from ..utils import utc_now


def _get_agent(db: Session, agent_id: str) -> Agent:
    agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
    if not agent:
        raise ValueError(f"Agent {agent_id!r} not found")
    return agent


def create_reminder(
    db: Session,
    agent_id: str,
    *,
    title: str,
    message: str,
    frequency: str,
    next_trigger_at: datetime,
) -> AuditReminder:
    agent = _get_agent(db, agent_id)
    reminder = AuditReminder(
        agent_id=agent.id,
        reminder_id=str(uuid.uuid4()),
        title=title,
        message=message,
        frequency=frequency,
        next_trigger_at=next_trigger_at,
        is_active=True,
        created_at=utc_now(),
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


def list_reminders(
    db: Session,
    agent_id: str,
    *,
    active_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditReminder]:
    agent = _get_agent(db, agent_id)
    q = db.query(AuditReminder).filter(AuditReminder.agent_id == agent.id)
    if active_only:
        q = q.filter(AuditReminder.is_active == True)  # noqa: E712
    return q.order_by(AuditReminder.next_trigger_at.asc()).offset(offset).limit(limit).all()


def get_reminder(db: Session, agent_id: str, reminder_id: str) -> AuditReminder:
    agent = _get_agent(db, agent_id)
    reminder = (
        db.query(AuditReminder)
        .filter(
            AuditReminder.agent_id == agent.id,
            AuditReminder.reminder_id == reminder_id,
        )
        .first()
    )
    if not reminder:
        raise ValueError(f"Reminder {reminder_id!r} not found for agent {agent_id!r}")
    return reminder


def update_reminder(
    db: Session,
    agent_id: str,
    reminder_id: str,
    *,
    title: str | None = None,
    message: str | None = None,
    frequency: str | None = None,
    next_trigger_at: datetime | None = None,
    is_active: bool | None = None,
) -> AuditReminder:
    reminder = get_reminder(db, agent_id, reminder_id)
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
    db.commit()
    db.refresh(reminder)
    return reminder


def delete_reminder(db: Session, agent_id: str, reminder_id: str) -> None:
    reminder = get_reminder(db, agent_id, reminder_id)
    db.delete(reminder)
    db.commit()


def trigger_reminder(db: Session, agent_id: str, reminder_id: str) -> AuditReminder:
    """Mark reminder as triggered, advance next_trigger_at based on frequency."""
    from datetime import timedelta

    reminder = get_reminder(db, agent_id, reminder_id)
    now = utc_now()
    reminder.last_triggered_at = now

    freq_delta = {
        "once": None,
        "daily": timedelta(days=1),
        "weekly": timedelta(weeks=1),
        "monthly": timedelta(days=30),
    }
    delta = freq_delta.get(reminder.frequency)
    if delta:
        reminder.next_trigger_at = now + delta
    else:
        # once — deactivate after trigger
        reminder.is_active = False

    db.commit()
    db.refresh(reminder)
    return reminder
