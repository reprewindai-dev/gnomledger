from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..dependencies import get_db, require_role
from ..schemas import AuditReminderCreate, AuditReminderResponse, AuditReminderUpdate
from ..services.reminder_service import ReminderService

router = APIRouter(tags=["reminders"])


class LegacyReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1)
    frequency: Literal["once", "daily", "weekly", "monthly"]
    next_trigger_at: datetime


def _create_payload(agent_id: str, body: LegacyReminderCreate) -> AuditReminderCreate:
    return AuditReminderCreate(agent_id=agent_id, **body.model_dump())


@router.get("/reminders/", response_model=list[AuditReminderResponse])
def list_reminders(
    agent_id: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> list[AuditReminderResponse]:
    return ReminderService(db).list_reminders(
        ctx.account_id,
        agent_id=agent_id,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )


@router.post("/reminders/", response_model=AuditReminderResponse, status_code=status.HTTP_201_CREATED)
def create_reminder(
    payload: AuditReminderCreate,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> AuditReminderResponse:
    try:
        return ReminderService(db).create_reminder(payload, ctx.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/reminders/{reminder_id}", response_model=AuditReminderResponse)
def get_reminder(
    reminder_id: str,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> AuditReminderResponse:
    try:
        return ReminderService(db).get_reminder(ctx.account_id, reminder_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/reminders/{reminder_id}", response_model=AuditReminderResponse)
def update_reminder(
    reminder_id: str,
    payload: AuditReminderUpdate,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> AuditReminderResponse:
    try:
        return ReminderService(db).update_reminder(
            ctx.account_id,
            reminder_id,
            title=payload.title,
            message=payload.message,
            frequency=payload.frequency,
            next_trigger_at=payload.next_trigger_at,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/reminders/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reminder(
    reminder_id: str,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> None:
    try:
        ReminderService(db).delete_reminder(ctx.account_id, reminder_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/reminders/{reminder_id}/trigger", response_model=AuditReminderResponse)
def trigger_reminder(
    reminder_id: str,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> AuditReminderResponse:
    try:
        return ReminderService(db).trigger_reminder(ctx.account_id, reminder_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/reminders", response_model=list[AuditReminderResponse])
def list_agent_reminders(
    agent_id: str,
    active_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> list[AuditReminderResponse]:
    return ReminderService(db).list_reminders(
        ctx.account_id,
        agent_id=agent_id,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )


@router.post("/agents/{agent_id}/reminders", response_model=AuditReminderResponse, status_code=status.HTTP_201_CREATED)
def create_agent_reminder(
    agent_id: str,
    payload: LegacyReminderCreate,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> AuditReminderResponse:
    try:
        return ReminderService(db).create_reminder(_create_payload(agent_id, payload), ctx.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/reminders/{reminder_id}", response_model=AuditReminderResponse)
def get_agent_reminder(
    agent_id: str,
    reminder_id: str,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> AuditReminderResponse:
    try:
        return ReminderService(db).get_reminder(ctx.account_id, reminder_id, agent_id=agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/agents/{agent_id}/reminders/{reminder_id}", response_model=AuditReminderResponse)
def update_agent_reminder(
    agent_id: str,
    reminder_id: str,
    payload: AuditReminderUpdate,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> AuditReminderResponse:
    try:
        return ReminderService(db).update_reminder(
            ctx.account_id,
            reminder_id,
            title=payload.title,
            message=payload.message,
            frequency=payload.frequency,
            next_trigger_at=payload.next_trigger_at,
            is_active=payload.is_active,
            agent_id=agent_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/agents/{agent_id}/reminders/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent_reminder(
    agent_id: str,
    reminder_id: str,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> None:
    try:
        ReminderService(db).delete_reminder(ctx.account_id, reminder_id, agent_id=agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
