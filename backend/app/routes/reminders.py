from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..dependencies import auth_context, get_db
from ..schemas import PGLRequestContext
from ..services import reminder_service

router = APIRouter(prefix="/agents/{agent_id}/reminders", tags=["reminders"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ReminderCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1)
    frequency: Literal["once", "daily", "weekly", "monthly"]
    next_trigger_at: datetime


class ReminderUpdate(BaseModel):
    title: str | None = None
    message: str | None = None
    frequency: Literal["once", "daily", "weekly", "monthly"] | None = None
    next_trigger_at: datetime | None = None
    is_active: bool | None = None


class ReminderOut(BaseModel):
    reminder_id: str
    agent_id: str
    title: str
    message: str
    frequency: str
    next_trigger_at: datetime
    last_triggered_at: datetime | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ReminderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create audit reminder",
)
def create_reminder(
    agent_id: str,
    body: ReminderCreate,
    db: Session = Depends(get_db),
    ctx: PGLRequestContext = Depends(auth_context),
):
    reminder = reminder_service.create_reminder(
        db,
        agent_id,
        title=body.title,
        message=body.message,
        frequency=body.frequency,
        next_trigger_at=body.next_trigger_at,
    )
    return _serialize(reminder, agent_id)


@router.get(
    "",
    response_model=list[ReminderOut],
    summary="List reminders for agent",
)
def list_reminders(
    agent_id: str,
    active_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    ctx: PGLRequestContext = Depends(auth_context),
):
    reminders = reminder_service.list_reminders(
        db, agent_id, active_only=active_only, limit=limit, offset=offset
    )
    return [_serialize(r, agent_id) for r in reminders]


@router.get(
    "/{reminder_id}",
    response_model=ReminderOut,
    summary="Get single reminder",
)
def get_reminder(
    agent_id: str,
    reminder_id: str,
    db: Session = Depends(get_db),
    ctx: PGLRequestContext = Depends(auth_context),
):
    reminder = reminder_service.get_reminder(db, agent_id, reminder_id)
    return _serialize(reminder, agent_id)


@router.patch(
    "/{reminder_id}",
    response_model=ReminderOut,
    summary="Update reminder",
)
def update_reminder(
    agent_id: str,
    reminder_id: str,
    body: ReminderUpdate,
    db: Session = Depends(get_db),
    ctx: PGLRequestContext = Depends(auth_context),
):
    reminder = reminder_service.update_reminder(
        db,
        agent_id,
        reminder_id,
        title=body.title,
        message=body.message,
        frequency=body.frequency,
        next_trigger_at=body.next_trigger_at,
        is_active=body.is_active,
    )
    return _serialize(reminder, agent_id)


@router.post(
    "/{reminder_id}/trigger",
    response_model=ReminderOut,
    summary="Manually trigger a reminder",
)
def trigger_reminder(
    agent_id: str,
    reminder_id: str,
    db: Session = Depends(get_db),
    ctx: PGLRequestContext = Depends(auth_context),
):
    reminder = reminder_service.trigger_reminder(db, agent_id, reminder_id)
    return _serialize(reminder, agent_id)


@router.delete(
    "/{reminder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete reminder",
)
def delete_reminder(
    agent_id: str,
    reminder_id: str,
    db: Session = Depends(get_db),
    ctx: PGLRequestContext = Depends(auth_context),
):
    reminder_service.delete_reminder(db, agent_id, reminder_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize(reminder, agent_id: str) -> dict:
    return {
        "reminder_id": reminder.reminder_id,
        "agent_id": agent_id,
        "title": reminder.title,
        "message": reminder.message,
        "frequency": reminder.frequency,
        "next_trigger_at": reminder.next_trigger_at,
        "last_triggered_at": reminder.last_triggered_at,
        "is_active": reminder.is_active,
        "created_at": reminder.created_at,
    }
