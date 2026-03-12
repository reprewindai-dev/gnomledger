from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import GenomePayload, GenomeUpdateRequest, LedgerEventCreate
from ..services.ledger_service import LedgerService
from ..utils import stable_hash, utc_now


class GenomeService:
    def __init__(self, db: Session):
        self.db = db
        self.ledger_service = LedgerService(db)

    def _get_agent(self, agent_id: str) -> models.Agent:
        agent = self.db.execute(
            select(models.Agent).where(models.Agent.agent_id == agent_id)
        ).scalar_one_or_none()
        if not agent:
            raise ValueError("Unknown agent_id")
        return agent

    def update_genome(self, agent_id: str, payload: GenomeUpdateRequest) -> GenomePayload:
        agent = self._get_agent(agent_id)
        latest_version = (
            self.db.execute(
                select(models.GenomeVersion)
                .where(models.GenomeVersion.agent_id == agent.id)
                .order_by(models.GenomeVersion.version.desc())
                .limit(1)
            )
        ).scalar_one()

        new_payload = latest_version.payload.copy()
        new_payload.update(payload.changes.model_dump())
        new_hash = stable_hash(new_payload)
        timestamp = utc_now()

        new_version = models.GenomeVersion(
            agent_id=agent.id,
            version=latest_version.version + 1,
            payload=new_payload,
            genome_hash=new_hash,
            note=payload.note,
            created_at=timestamp,
        )
        self.db.add(new_version)

        certificate = (
            self.db.execute(
                select(models.BirthCertificate).where(models.BirthCertificate.agent_id == agent.id)
            ).scalar_one()
        )
        certificate.genome_hash = new_hash

        self.db.commit()

        self.ledger_service.log_event(
            LedgerEventCreate(
                agent_id=agent.agent_id,
                event_type="mutation_update",
                actor=payload.changes.intended_use if payload.changes.intended_use else agent.creator,
                summary=payload.note,
                details={"genome_hash": new_hash, "note": payload.note},
            )
        )

        return GenomePayload(**new_payload)
