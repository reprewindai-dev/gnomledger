from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, require_role
from ..schemas import IncidentCreate, IncidentResponse, IncidentUpdate
from ..services.incident_service import IncidentService

router = APIRouter(prefix="/incidents")


@router.get("/", response_model=list[IncidentResponse])
def list_incidents(
    agent_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> list[IncidentResponse]:
    service = IncidentService(db)
    return service.list_incidents(agent_id=agent_id, status=status_filter)


@router.post("/", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
    _ctx=Depends(require_role("operator", "admin", "owner")),
) -> IncidentResponse:
    service = IncidentService(db)
    try:
        return service.create_incident(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/{incident_id}", response_model=IncidentResponse)
def update_incident(
    incident_id: str,
    payload: IncidentUpdate,
    db: Session = Depends(get_db),
    _ctx=Depends(require_role("operator", "admin", "owner")),
) -> IncidentResponse:
    service = IncidentService(db)
    try:
        return service.update_incident(incident_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
