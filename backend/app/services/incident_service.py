from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from ..models import Agent, IncidentRecord
from ..utils import utc_now


def _get_agent(db: Session, agent_id: str, account_id: int | None = None) -> Agent:
    # account_id scopes the lookup to the caller's tenant; a foreign agent reads as not found.
    q = db.query(Agent).filter(Agent.agent_id == agent_id)
    if account_id is not None:
        q = q.filter(Agent.account_id == account_id)
    agent = q.first()
    if not agent:
        raise ValueError(f"Agent {agent_id!r} not found")
    return agent


def create_incident(
    db: Session,
    agent_id: str,
    *,
    severity: str,
    title: str,
    description: str,
    reporter: str,
    account_id: int | None = None,
) -> IncidentRecord:
    agent = _get_agent(db, agent_id, account_id)
    record = IncidentRecord(
        agent_id=agent.id,
        incident_id=str(uuid.uuid4()),
        severity=severity,
        status="open",
        title=title,
        description=description,
        reporter=reporter,
        created_at=utc_now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_incidents(
    db: Session,
    agent_id: str,
    *,
    status: str | None = None,
    severity: str | None = None,
    limit: int = 50,
    offset: int = 0,
    account_id: int | None = None,
) -> list[IncidentRecord]:
    agent = _get_agent(db, agent_id, account_id)
    q = db.query(IncidentRecord).filter(IncidentRecord.agent_id == agent.id)
    if status:
        q = q.filter(IncidentRecord.status == status)
    if severity:
        q = q.filter(IncidentRecord.severity == severity)
    return q.order_by(IncidentRecord.created_at.desc()).offset(offset).limit(limit).all()


def get_incident(
    db: Session, agent_id: str, incident_id: str, *, account_id: int | None = None
) -> IncidentRecord:
    agent = _get_agent(db, agent_id, account_id)
    record = (
        db.query(IncidentRecord)
        .filter(
            IncidentRecord.agent_id == agent.id,
            IncidentRecord.incident_id == incident_id,
        )
        .first()
    )
    if not record:
        raise ValueError(f"Incident {incident_id!r} not found for agent {agent_id!r}")
    return record


def update_incident(
    db: Session,
    agent_id: str,
    incident_id: str,
    *,
    status: str | None = None,
    resolution_notes: str | None = None,
    account_id: int | None = None,
) -> IncidentRecord:
    record = get_incident(db, agent_id, incident_id, account_id=account_id)
    if status:
        record.status = status
        if status in ("resolved", "closed") and record.resolved_at is None:
            record.resolved_at = utc_now()
    if resolution_notes is not None:
        record.resolution_notes = resolution_notes
    db.commit()
    db.refresh(record)
    return record


def delete_incident(
    db: Session, agent_id: str, incident_id: str, *, account_id: int | None = None
) -> None:
    record = get_incident(db, agent_id, incident_id, account_id=account_id)
    db.delete(record)
    db.commit()
