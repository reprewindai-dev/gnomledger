from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..schemas import (
    LEGACY_GENOME_FIELDS,
    SINGLE_MODEL_FIELDS,
    GenomePayload,
    GenomeUpdateRequest,
    LedgerEventCreate,
)
from ..services.ledger_service import LedgerService
from ..utils import stable_hash, utc_now
from .principal import principal_label


class GenomeConflict(ValueError):
    """The genome cannot be changed in its current state (raced update, decommissioned)."""


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
        changed_by: dict[str, Any] | None = None,
    ) -> GenomePayload:
        agent = self._get_agent(agent_id, account_id)
        result: dict[str, Any] = {}

        def add_version(locked: models.Agent) -> dict[str, Any]:
            # Runs with the agent row locked, so the version read here is the latest one and
            # the new version commits together with its change record.
            if locked.status == "decommissioned":
                raise GenomeConflict("Agent is decommissioned; its genome can no longer change")
            latest_version = self.db.execute(
                select(models.GenomeVersion)
                .where(models.GenomeVersion.agent_id == locked.id)
                .order_by(models.GenomeVersion.version.desc())
                .limit(1)
            ).scalar_one()

            # The original genome fields are replaced as before (changes is a full genome);
            # the accountability fields are merged, so a client that predates them cannot
            # erase them by omission.
            current = GenomePayload(**latest_version.payload)
            replaced = payload.changes.model_dump(
                include=(set(LEGACY_GENOME_FIELDS) - set(SINGLE_MODEL_FIELDS))
                | payload.changes.model_fields_set
            )
            new_payload = GenomePayload(**{**current.model_dump(), **replaced}).canonical()
            new_hash = stable_hash(new_payload)
            if new_hash == latest_version.genome_hash:
                raise ValueError("Genome content unchanged")

            previous_payload = latest_version.payload
            changed_fields = sorted(
                name
                for name in set(previous_payload) | set(new_payload)
                if previous_payload.get(name) != new_payload.get(name)
            )
            new_version = models.GenomeVersion(
                agent_id=locked.id,
                version=latest_version.version + 1,
                payload=new_payload,
                genome_hash=new_hash,
                note=payload.note,
                created_at=utc_now(),
            )
            self.db.add(new_version)
            certificate = self.db.execute(
                select(models.BirthCertificate).where(models.BirthCertificate.agent_id == locked.id)
            ).scalar_one()
            # The signed birth certificate document is not touched; this column tracks the
            # current genome for existing readers.
            certificate.genome_hash = new_hash
            result["payload"] = new_payload
            return {
                "previous_version": latest_version.version,
                "new_version": new_version.version,
                "previous_genome_hash": latest_version.genome_hash,
                "new_genome_hash": new_hash,
                "genome_hash": new_hash,  # kept for readers of the original event shape
                "changed_fields": changed_fields,
            }

        try:
            self.ledger_service.log_event(
                LedgerEventCreate(
                    agent_id=agent.agent_id,
                    event_type="mutation_update",
                    actor=principal_label(changed_by),
                    summary=payload.note,
                    details={
                        "change": "genome_update",
                        "changed_by": changed_by,
                        "declared_actor": payload.actor,
                        "reason": payload.reason,
                        "note": payload.note,
                    },
                ),
                account_id=account_id,
                prepare=add_version,
            )
        except IntegrityError as exc:
            raise GenomeConflict(
                "Genome was changed concurrently; retry against the latest version"
            ) from exc

        return GenomePayload(**result["payload"])
