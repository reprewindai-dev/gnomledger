from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import LEGACY_GENOME_FIELDS, GenomePayload, GenomeUpdateRequest, LedgerEventCreate
from ..services.ledger_service import LedgerService
from ..utils import stable_hash, utc_now


class GenomeService:
    def __init__(self, db: Session):
        self.db = db
        self.ledger_service = LedgerService(db)

    def _get_agent(self, agent_id: str, account_id: int | None = None) -> models.Agent:
        # account_id scopes the lookup to the caller's tenant; a foreign agent reads as unknown.
        stmt = select(models.Agent).where(models.Agent.agent_id == agent_id)
        if account_id is not None:
            stmt = stmt.where(models.Agent.account_id == account_id)
        agent = self.db.execute(stmt).scalar_one_or_none()
        if not agent:
            raise ValueError("Unknown agent_id")
        return agent

    def update_genome(
        self,
        agent_id: str,
        payload: GenomeUpdateRequest,
        *,
        account_id: int | None = None,
    ) -> GenomePayload:
        agent = self._get_agent(agent_id, account_id)
        latest_version = (
            self.db.execute(
                select(models.GenomeVersion)
                .where(models.GenomeVersion.agent_id == agent.id)
                .order_by(models.GenomeVersion.version.desc())
                .limit(1)
            )
        ).scalar_one()

        # The original genome fields are replaced as before (changes is a full genome); the
        # accountability fields are merged, so a client that predates them cannot erase them
        # by omission.
        current = GenomePayload(**latest_version.payload)
        replaced = payload.changes.model_dump(
            include=set(LEGACY_GENOME_FIELDS) | payload.changes.model_fields_set
        )
        new_payload = GenomePayload(**{**current.model_dump(), **replaced}).canonical()
        new_hash = stable_hash(new_payload)
        timestamp = utc_now()
        if new_hash == latest_version.genome_hash:
            raise ValueError("Genome content unchanged")

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
        self.db.refresh(certificate)

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
