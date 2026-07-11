from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, require_role
from ..schemas import AuditReminderCreate, AuditReminderResponse
from ..services.reminder_service import ReminderService

router = APIRouter(prefix="/reminders")


@router.get("/", response_model=list[AuditReminderResponse])
def list_reminders(
    agent_id: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> list[AuditReminderResponse]:
    service = ReminderService(db)
    return service.list_reminders(agent_id=agent_id, active_only=active_only)


@router.post("/", response_model=AuditReminderResponse, status_code=status.HTTP_201_CREATED)
def create_reminder(
    payload: AuditReminderCreate,
    db: Session = Depends(get_db),
    _ctx=Depends(require_role("operator", "admin", "owner")),
) -> AuditReminderResponse:
    service = ReminderService(db)
    try:
        return service.create_reminder(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_reminder(
    reminder_id: str,
    db: Session = Depends(get_db),
    _ctx=Depends(require_role("operator", "admin", "owner")),
) -> None:
    service = ReminderService(db)
    try:
        service.delete_reminder(reminder_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
