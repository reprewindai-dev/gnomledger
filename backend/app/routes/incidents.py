from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..dependencies import get_db, require_role
from ..schemas import IncidentCreate, IncidentResponse, IncidentUpdate
from ..services.incident_service import IncidentService

router = APIRouter(tags=["incidents"])


class LegacyIncidentCreate(BaseModel):
    severity: Literal["low", "medium", "high", "critical"]
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    reporter: str = Field(min_length=1, max_length=255)


def _create_payload(agent_id: str, body: LegacyIncidentCreate) -> IncidentCreate:
    return IncidentCreate(agent_id=agent_id, **body.model_dump())


@router.get("/incidents/", response_model=list[IncidentResponse])
def list_incidents(
    agent_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> list[IncidentResponse]:
    return IncidentService(db).list_incidents(
        agent_id=agent_id,
        status=status_filter,
        severity=severity,
        limit=limit,
        offset=offset,
        account_id=ctx.account_id,
    )


@router.post("/incidents/", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> IncidentResponse:
    try:
        return IncidentService(db).create_incident(payload, account_id=ctx.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/incidents/{incident_id}", response_model=IncidentResponse)
def get_incident(
    incident_id: str,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> IncidentResponse:
    try:
        return IncidentService(db).get_incident(incident_id, account_id=ctx.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/incidents/{incident_id}", response_model=IncidentResponse)
def update_incident(
    incident_id: str,
    payload: IncidentUpdate,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> IncidentResponse:
    try:
        return IncidentService(db).update_incident(
            incident_id, payload, account_id=ctx.account_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/incidents/{incident_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_incident(
    incident_id: str,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> None:
    try:
        IncidentService(db).delete_incident(incident_id, account_id=ctx.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/incidents", response_model=list[IncidentResponse])
def list_agent_incidents(
    agent_id: str,
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> list[IncidentResponse]:
    return IncidentService(db).list_incidents(
        agent_id=agent_id,
        status=status_filter,
        severity=severity,
        limit=limit,
        offset=offset,
        account_id=ctx.account_id,
    )


@router.post("/agents/{agent_id}/incidents", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_agent_incident(
    agent_id: str,
    payload: LegacyIncidentCreate,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> IncidentResponse:
    try:
        return IncidentService(db).create_incident(
            _create_payload(agent_id, payload), account_id=ctx.account_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/incidents/{incident_id}", response_model=IncidentResponse)
def get_agent_incident(
    agent_id: str,
    incident_id: str,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> IncidentResponse:
    try:
        return IncidentService(db).get_incident(
            incident_id, agent_id=agent_id, account_id=ctx.account_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/agents/{agent_id}/incidents/{incident_id}", response_model=IncidentResponse)
def update_agent_incident(
    agent_id: str,
    incident_id: str,
    payload: IncidentUpdate,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> IncidentResponse:
    try:
        return IncidentService(db).update_incident(
            incident_id, payload, agent_id=agent_id, account_id=ctx.account_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/agents/{agent_id}/incidents/{incident_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent_incident(
    agent_id: str,
    incident_id: str,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> None:
    try:
        IncidentService(db).delete_incident(
            incident_id, agent_id=agent_id, account_id=ctx.account_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
