from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..dependencies import auth_context, get_db
from ..schemas import PGLRequestContext
from ..services import incident_service

router = APIRouter(prefix="/agents/{agent_id}/incidents", tags=["incidents"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class IncidentCreate(BaseModel):
    severity: Literal["low", "medium", "high", "critical"]
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    reporter: str = Field(..., min_length=1, max_length=255)


class IncidentUpdate(BaseModel):
    status: Literal["open", "investigating", "resolved", "closed"] | None = None
    resolution_notes: str | None = None


class IncidentOut(BaseModel):
    incident_id: str
    agent_id: str
    severity: str
    status: str
    title: str
    description: str
    reporter: str
    resolution_notes: str | None
    created_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=IncidentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create incident",
)
def create_incident(
    agent_id: str,
    body: IncidentCreate,
    db: Session = Depends(get_db),
    ctx: PGLRequestContext = Depends(auth_context),
):
    record = incident_service.create_incident(
        db,
        agent_id,
        severity=body.severity,
        title=body.title,
        description=body.description,
        reporter=body.reporter,
    )
    return _serialize(record, agent_id)


@router.get(
    "",
    response_model=list[IncidentOut],
    summary="List incidents for agent",
)
def list_incidents(
    agent_id: str,
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    ctx: PGLRequestContext = Depends(auth_context),
):
    records = incident_service.list_incidents(
        db, agent_id, status=status_filter, severity=severity, limit=limit, offset=offset
    )
    return [_serialize(r, agent_id) for r in records]


@router.get(
    "/{incident_id}",
    response_model=IncidentOut,
    summary="Get single incident",
)
def get_incident(
    agent_id: str,
    incident_id: str,
    db: Session = Depends(get_db),
    ctx: PGLRequestContext = Depends(auth_context),
):
    record = incident_service.get_incident(db, agent_id, incident_id)
    return _serialize(record, agent_id)


@router.patch(
    "/{incident_id}",
    response_model=IncidentOut,
    summary="Update incident status / resolution",
)
def update_incident(
    agent_id: str,
    incident_id: str,
    body: IncidentUpdate,
    db: Session = Depends(get_db),
    ctx: PGLRequestContext = Depends(auth_context),
):
    record = incident_service.update_incident(
        db,
        agent_id,
        incident_id,
        status=body.status,
        resolution_notes=body.resolution_notes,
    )
    return _serialize(record, agent_id)


@router.delete(
    "/{incident_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete incident",
)
def delete_incident(
    agent_id: str,
    incident_id: str,
    db: Session = Depends(get_db),
    ctx: PGLRequestContext = Depends(auth_context),
):
    incident_service.delete_incident(db, agent_id, incident_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize(record, agent_id: str) -> dict:
    return {
        "incident_id": record.incident_id,
        "agent_id": agent_id,
        "severity": record.severity,
        "status": record.status,
        "title": record.title,
        "description": record.description,
        "reporter": record.reporter,
        "resolution_notes": record.resolution_notes,
        "created_at": record.created_at,
        "resolved_at": record.resolved_at,
    }
