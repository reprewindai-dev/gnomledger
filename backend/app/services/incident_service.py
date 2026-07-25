from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import IncidentCreate, IncidentResponse, IncidentUpdate
from ..utils import short_id, utc_now
from .analytics_service import AnalyticsService


def _to_response(incident: models.IncidentRecord, agent_public_id: str) -> IncidentResponse:
    return IncidentResponse(
        incident_id=incident.incident_id,
        agent_id=agent_public_id,
        severity=incident.severity,
        status=incident.status,
        title=incident.title,
        description=incident.description,
        reporter=incident.reporter,
        resolution_notes=incident.resolution_notes,
        created_at=incident.created_at,
        resolved_at=incident.resolved_at,
    )


class IncidentService:
    def __init__(self, db: Session):
        self.db = db
        self.analytics_service = AnalyticsService(db)

    def _get_agent(self, agent_id: str, account_id: int | None = None) -> models.Agent:
        stmt = select(models.Agent).where(models.Agent.agent_id == agent_id)
        if account_id is not None:
            stmt = stmt.where(models.Agent.account_id == account_id)
        agent = self.db.execute(stmt).scalar_one_or_none()
        if not agent:
            raise ValueError("Unknown agent_id")
        return agent

    def create_incident(
        self, payload: IncidentCreate, account_id: int | None = None
    ) -> IncidentResponse:
        agent = self._get_agent(payload.agent_id, account_id)
        incident = models.IncidentRecord(
            agent_id=agent.id,
            incident_id=short_id("inc"),
            severity=payload.severity,
            status="open",
            title=payload.title,
            description=payload.description,
            reporter=payload.reporter,
            created_at=utc_now(),
        )
        self.db.add(incident)
        self.db.commit()
        self.db.refresh(incident)
        self.analytics_service.track(
            event_type="incident_created",
            account_id=agent.account_id,
            payload={
                "agent_id": agent.agent_id,
                "incident_id": incident.incident_id,
                "severity": incident.severity,
            },
        )
        return _to_response(incident, agent.agent_id)

    def list_incidents(
        self,
        agent_id: str | None = None,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 200,
        offset: int = 0,
        account_id: int | None = None,
    ) -> list[IncidentResponse]:
        stmt = (
            select(models.IncidentRecord, models.Agent)
            .join(models.Agent, models.IncidentRecord.agent_id == models.Agent.id)
            .order_by(models.IncidentRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if account_id is not None:
            stmt = stmt.where(models.Agent.account_id == account_id)
        if agent_id:
            stmt = stmt.where(models.Agent.agent_id == agent_id)
        if status:
            stmt = stmt.where(models.IncidentRecord.status == status)
        if severity:
            stmt = stmt.where(models.IncidentRecord.severity == severity)
        rows = self.db.execute(stmt).all()
        return [_to_response(incident, agent.agent_id) for incident, agent in rows]

    def get_incident(
        self,
        incident_id: str,
        agent_id: str | None = None,
        account_id: int | None = None,
    ) -> IncidentResponse:
        stmt = (
            select(models.IncidentRecord, models.Agent)
            .join(models.Agent, models.IncidentRecord.agent_id == models.Agent.id)
            .where(models.IncidentRecord.incident_id == incident_id)
        )
        if account_id is not None:
            stmt = stmt.where(models.Agent.account_id == account_id)
        if agent_id:
            stmt = stmt.where(models.Agent.agent_id == agent_id)
        row = self.db.execute(stmt).one_or_none()
        if not row:
            raise ValueError("Unknown incident_id")
        incident, agent = row
        return _to_response(incident, agent.agent_id)

    def update_incident(
        self,
        incident_id: str,
        payload: IncidentUpdate,
        agent_id: str | None = None,
        account_id: int | None = None,
    ) -> IncidentResponse:
        stmt = (
            select(models.IncidentRecord, models.Agent)
            .join(models.Agent, models.IncidentRecord.agent_id == models.Agent.id)
            .where(models.IncidentRecord.incident_id == incident_id)
        )
        if account_id is not None:
            stmt = stmt.where(models.Agent.account_id == account_id)
        if agent_id:
            stmt = stmt.where(models.Agent.agent_id == agent_id)
        row = self.db.execute(stmt).one_or_none()
        if not row:
            raise ValueError("Unknown incident_id")
        incident, agent = row
        if payload.status is not None:
            incident.status = payload.status
            if payload.status in ("resolved", "closed") and incident.resolved_at is None:
                incident.resolved_at = utc_now()
        if payload.resolution_notes is not None:
            incident.resolution_notes = payload.resolution_notes
        self.db.commit()
        self.db.refresh(incident)
        self.analytics_service.track(
            event_type="incident_updated",
            account_id=agent.account_id,
            payload={
                "agent_id": agent.agent_id,
                "incident_id": incident.incident_id,
                "status": incident.status,
            },
        )
        return _to_response(incident, agent.agent_id)

    def delete_incident(
        self,
        incident_id: str,
        agent_id: str | None = None,
        account_id: int | None = None,
    ) -> None:
        stmt = (
            select(models.IncidentRecord)
            .join(models.Agent)
            .where(models.IncidentRecord.incident_id == incident_id)
        )
        if account_id is not None:
            stmt = stmt.where(models.Agent.account_id == account_id)
        if agent_id:
            stmt = stmt.where(models.Agent.agent_id == agent_id)
        incident = self.db.execute(stmt).scalar_one_or_none()
        if not incident:
            raise ValueError("Unknown incident_id")
        self.db.delete(incident)
        self.db.commit()
