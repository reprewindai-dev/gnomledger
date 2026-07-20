from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .. import models
from ..schemas import LedgerEventCreate, LedgerEventResponse
from ..utils import canonical_timestamp, short_id, stable_hash, utc_now
from .analytics_service import AnalyticsService
from .merkle_service import MerkleTree


class LedgerService:
    def __init__(self, db: Session):
        self.db = db
        self.analytics_service = AnalyticsService(db)

    def _latest_event(self, agent_db_id: int) -> models.LedgerEvent | None:
        stmt = (
            select(models.LedgerEvent)
            .where(models.LedgerEvent.agent_id == agent_db_id)
            .order_by(models.LedgerEvent.created_at.desc(), models.LedgerEvent.id.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def log_event(self, payload: LedgerEventCreate) -> LedgerEventResponse:
        agent = self.db.execute(
            select(models.Agent).where(models.Agent.agent_id == payload.agent_id)
        ).scalar_one_or_none()
        if not agent:
            raise ValueError("Unknown agent_id")

        previous = self._latest_event(agent.id)
        prev_hash = previous.event_hash if previous else None

        if payload.idempotency_key:
            existing = self.db.execute(
                select(models.LedgerEvent).where(
                    models.LedgerEvent.idempotency_key == payload.idempotency_key,
                    models.LedgerEvent.agent_id == agent.id,
                )
            ).scalar_one_or_none()
            if existing:
                return LedgerEventResponse(
                    event_id=existing.event_id,
                    event_type=existing.event_type,
                    actor=existing.actor,
                    summary=existing.summary,
                    details=existing.details,
                    prev_event_hash=existing.prev_event_hash,
                    event_hash=existing.event_hash,
                    tier=existing.tier,
                    batch_id=existing.batch_id,
                    created_at=existing.created_at,
                )

        event = models.LedgerEvent(
            agent_id=agent.id,
            event_id=short_id("evt"),
            event_type=payload.event_type,
            actor=payload.actor,
            summary=payload.summary,
            details=payload.details,
            prev_event_hash=prev_hash,
            tier=payload.tier,
            batch_id=payload.batch_id,
            created_at=utc_now(),
            idempotency_key=payload.idempotency_key,
            event_hash="",
        )
        event.event_hash = stable_hash(
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "agent_id": agent.agent_id,
                "actor": event.actor,
                "summary": event.summary,
                "details": event.details,
                "prev_event_hash": event.prev_event_hash,
                "tier": event.tier,
                "batch_id": event.batch_id,
                "created_at": canonical_timestamp(event.created_at),
            }
        )
        self.db.add(event)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            # duplicate idempotency key path for race conditions
            if payload.idempotency_key:
                existing = self.db.execute(
                    select(models.LedgerEvent).where(
                        models.LedgerEvent.idempotency_key == payload.idempotency_key,
                        models.LedgerEvent.agent_id == agent.id,
                    )
                ).scalar_one_or_none()
                if existing:
                    return LedgerEventResponse(
                        event_id=existing.event_id,
                        event_type=existing.event_type,
                        actor=existing.actor,
                        summary=existing.summary,
                        details=existing.details,
                        prev_event_hash=existing.prev_event_hash,
                        event_hash=existing.event_hash,
                        tier=existing.tier,
                        batch_id=existing.batch_id,
                        created_at=existing.created_at,
                    )
            raise
        self.db.refresh(event)

        self.analytics_service.track(
            event_type=f"ledger_{event.event_type}",
            account_id=agent.account_id,
            payload={
                "agent_id": agent.agent_id,
                "event_id": event.event_id,
                "event_type": event.event_type,
            },
        )

        return LedgerEventResponse(
            event_id=event.event_id,
            event_type=event.event_type,
            actor=event.actor,
            summary=event.summary,
            details=event.details,
            prev_event_hash=event.prev_event_hash,
            event_hash=event.event_hash,
            tier=event.tier,
            batch_id=event.batch_id,
            created_at=event.created_at,
        )

    def batch_events(self, agent_id: str, batch_id: str) -> LedgerEventResponse | None:
        agent = self.db.execute(
            select(models.Agent).where(models.Agent.agent_id == agent_id)
        ).scalar_one_or_none()
        if not agent:
            raise ValueError("Unknown agent_id")
            
        unbatched = list(self.db.execute(
            select(models.LedgerEvent)
            .where(models.LedgerEvent.agent_id == agent.id, models.LedgerEvent.batch_id == None, models.LedgerEvent.tier == 4)
            .order_by(models.LedgerEvent.id.asc())
        ).scalars())
        
        if not unbatched:
            return None
            
        leaves = [e.event_hash for e in unbatched]
        tree = MerkleTree(leaves)
        root_hash = tree.get_root()
        
        for e in unbatched:
            e.batch_id = batch_id
            
        # Create the tier 3 anchor event
        payload = LedgerEventCreate(
            agent_id=agent_id,
            event_type="batch_anchor",
            actor="system",
            summary=f"Merkle Batch Anchor for {len(unbatched)} events",
            details={"merkle_root": root_hash, "leaf_count": len(unbatched)},
            tier=3,
            batch_id=batch_id
        )
        return self.log_event(payload)

    def get_agent_history(
        self,
        agent_id: str,
        limit: int = 100,
        cursor: int | None = None,
    ) -> list[LedgerEventResponse]:
        agent = self.db.execute(
            select(models.Agent).where(models.Agent.agent_id == agent_id)
        ).scalar_one_or_none()
        if not agent:
            raise ValueError("Unknown agent_id")

        stmt = (
            select(models.LedgerEvent)
            .where(models.LedgerEvent.agent_id == agent.id)
            .order_by(models.LedgerEvent.created_at.asc(), models.LedgerEvent.id.asc())
        )
        if cursor is not None:
            stmt = stmt.where(models.LedgerEvent.id > cursor)
        stmt = stmt.limit(limit)
        events: Iterable[models.LedgerEvent] = self.db.scalars(stmt)
        return [
            LedgerEventResponse(
                event_id=e.event_id,
                event_type=e.event_type,
                actor=e.actor,
                summary=e.summary,
                details=e.details,
                prev_event_hash=e.prev_event_hash,
                event_hash=e.event_hash,
                tier=e.tier,
                batch_id=e.batch_id,
                created_at=e.created_at,
            )
            for e in events
        ]

    def verify_chain(self, agent_id: str) -> tuple[bool, dict[str, object]]:
        agent = self.db.execute(
            select(models.Agent).where(models.Agent.agent_id == agent_id)
        ).scalar_one_or_none()
        if not agent:
            raise ValueError("Unknown agent_id")

        events = list(
            self.db.execute(
                select(models.LedgerEvent)
                .where(models.LedgerEvent.agent_id == agent.id)
                .order_by(models.LedgerEvent.created_at.asc(), models.LedgerEvent.id.asc())
            ).scalars()
        )

        errors: list[str] = []
        latest_hash = None
        previous: str | None = None
        first_event_at = None
        last_event_at = None

        for event in events:
            if first_event_at is None:
                first_event_at = event.created_at
            last_event_at = event.created_at

            expected = stable_hash(
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "agent_id": agent.agent_id,
                    "actor": event.actor,
                    "summary": event.summary,
                    "details": event.details,
                    "prev_event_hash": previous,
                    "tier": event.tier,
                    "batch_id": event.batch_id,
                    "created_at": canonical_timestamp(event.created_at),
                }
            )
            if expected != event.event_hash:
                errors.append(f"event_hash mismatch at {event.event_id}")
            if event.prev_event_hash != previous:
                errors.append(f"chain break at {event.event_id}")
            previous = event.event_hash
            latest_hash = event.event_hash

        return (
            len(errors) == 0,
            {
                "valid": len(errors) == 0,
                "checked_events": len(events),
                "first_event_at": first_event_at,
                "last_event_at": last_event_at,
                "latest_event_hash": latest_hash,
                "errors": errors,
            },
        )
