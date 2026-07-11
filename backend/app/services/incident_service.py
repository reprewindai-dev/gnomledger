from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import IncidentCreate, IncidentResponse, IncidentUpdate
from ..utils import short_id, utc_now
from .analytics_service import AnalyticsService


def _to_response(inc: models.IncidentRecord, agent_public_id: str) -> IncidentResponse:
    return IncidentResponse(
        incident_id=inc.incident_id,
        agent_id=agent_public_id,
        severity=inc.severity,
        status=inc.status,
        title=inc.title,
        description=inc.description,
        reporter=inc.reporter,
        resolution_notes=inc.resolution_notes,
        created_at=inc.created_at,
        resolved_at=inc.resolved_at,
    )


class IncidentService:
    def __init__(self, db: Session):
        self.db = db
        self.analytics_service = AnalyticsService(db)

    def _get_agent(self, agent_id: str) -> models.Agent:
        agent = self.db.execute(
            select(models.Agent).where(models.Agent.agent_id == agent_id)
        ).scalar_one_or_none()
        if not agent:
            raise ValueError("Unknown agent_id")
        return agent

    def create_incident(self, payload: IncidentCreate) -> IncidentResponse:
        agent = self._get_agent(payload.agent_id)

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
            payload={"agent_id": agent.agent_id, "incident_id": incident.incident_id, "severity": incident.severity},
        )

        return _to_response(incident, agent.agent_id)

    def list_incidents(self, agent_id: str | None = None, status: str | None = None) -> list[IncidentResponse]:
        stmt = select(models.IncidentRecord, models.Agent).join(models.Agent, models.IncidentRecord.agent_id == models.Agent.id)
        if agent_id:
            stmt = stmt.where(models.Agent.agent_id == agent_id)
        if status:
            stmt = stmt.where(models.IncidentRecord.status == status)
        stmt = stmt.order_by(models.IncidentRecord.created_at.desc())

        rows = self.db.execute(stmt).all()
        return [_to_response(inc, agent.agent_id) for inc, agent in rows]

    def update_incident(self, incident_id: str, payload: IncidentUpdate) -> IncidentResponse:
        row = self.db.execute(
            select(models.IncidentRecord, models.Agent)
            .join(models.Agent, models.IncidentRecord.agent_id == models.Agent.id)
            .where(models.IncidentRecord.incident_id == incident_id)
        ).one_or_none()
        if not row:
            raise ValueError("Unknown incident_id")
        incident, agent = row

        incident.status = payload.status
        if payload.resolution_notes is not None:
            incident.resolution_notes = payload.resolution_notes
        if payload.status in ("resolved", "closed") and incident.resolved_at is None:
            incident.resolved_at = utc_now()

        self.db.commit()
        self.db.refresh(incident)

        self.analytics_service.track(
            event_type="incident_updated",
            account_id=agent.account_id,
            payload={"agent_id": agent.agent_id, "incident_id": incident.incident_id, "status": incident.status},
        )

        return _to_response(incident, agent.agent_id)
