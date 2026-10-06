from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..schemas import LedgerEventCreate, LedgerEventResponse
from ..utils import canonical_timestamp, short_id, stable_hash, utc_now
from .analytics_service import AnalyticsService

_SQLITE_APPEND_LOCK = threading.Lock()

PrepareHook = Callable[[models.Agent], "dict[str, Any] | None"]


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

    def _resolve_agent(self, agent_id: str, account_id: int | None) -> models.Agent:
        # account_id scopes the lookup to the caller's tenant. A foreign agent is reported
        # exactly like an unknown one so a route cannot leak that it exists.
        stmt = select(models.Agent).where(models.Agent.agent_id == agent_id)
        if account_id is not None:
            stmt = stmt.where(models.Agent.account_id == account_id)
        agent = self.db.execute(stmt).scalar_one_or_none()
        if not agent:
            raise ValueError("Unknown agent_id")
        return agent

    def log_event(
        self,
        payload: LedgerEventCreate,
        *,
        account_id: int | None = None,
        prepare: PrepareHook | None = None,
    ) -> LedgerEventResponse:
        """Append one event to the agent's chain.

        prepare, if given, runs after the agent row is locked and before the event is built,
        in the same transaction: it may change the locked agent or add rows (a genome version,
        a status change) and returns details to merge into the event. Its writes and the event
        commit together or not at all. It may raise to abort the append.
        """
        connection = self.db.connection()
        if connection.dialect.name != "sqlite":
            try:
                return self._append_event(payload, account_id, prepare)
            except Exception:
                self.db.rollback()
                raise
        # SQLite has no row locks and ignores FOR UPDATE, and the driver opens a transaction
        # only at the first write, after the chain head has been read. So the append takes
        # the database write lock before that read (this also covers other processes). The
        # process lock queues this process's writers; SQLite's own lock wait is an unfair
        # retry loop that times writers out under sustained contention. An open transaction
        # means this session has already written and holds the database lock.
        with _SQLITE_APPEND_LOCK:
            try:
                if not connection.connection.dbapi_connection.in_transaction:
                    connection.exec_driver_sql("BEGIN IMMEDIATE")
                return self._append_event(payload, account_id, prepare)
            finally:
                # Never leave the process lock while still holding the database lock.
                if self.db.in_transaction():
                    self.db.rollback()

    def _append_event(
        self,
        payload: LedgerEventCreate,
        account_id: int | None,
        prepare: PrepareHook | None = None,
    ) -> LedgerEventResponse:
        # Appends to one agent's chain are serialized on the agent row. Without the lock two
        # concurrent appends read the same chain head and both link to it, forking the chain
        # (observed: lineage-reformation run lre-20261005T001846Z, verify "blocked").
        # populate_existing: the locked read must return the committed row, not a cached one.
        stmt = select(models.Agent).where(models.Agent.agent_id == payload.agent_id)
        if account_id is not None:
            stmt = stmt.where(models.Agent.account_id == account_id)
        agent = self.db.execute(
            stmt.with_for_update().execution_options(populate_existing=True)
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
                    created_at=existing.created_at,
                    persisted=True,
                    idempotent_replay=True,
                    chain_head=existing.event_hash,
                )

        if prepare is not None:
            extra = prepare(agent)
            if extra:
                payload = payload.model_copy(update={"details": {**payload.details, **extra}})
            self.db.flush()

        event = models.LedgerEvent(
            agent_id=agent.id,
            event_id=short_id("evt"),
            event_type=payload.event_type,
            actor=payload.actor,
            summary=payload.summary,
            details=payload.details,
            prev_event_hash=prev_hash,
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
                "created_at": canonical_timestamp(event.created_at),
            }
        )
        self.db.add(event)

        # Recalculate trust snapshot and save to DB in same transaction
        from .trust_policy import TrustPolicyV1

        # Only these event types move the V1 trust score, so only they are loaded (in chain
        # order). Loading the agent's whole history on every append made each append O(n).
        scoring_events = list(
            self.db.execute(
                select(models.LedgerEvent)
                .where(
                    models.LedgerEvent.agent_id == agent.id,
                    models.LedgerEvent.event_type.in_(TrustPolicyV1.SCORING_EVENT_TYPES),
                )
                .order_by(models.LedgerEvent.created_at.asc(), models.LedgerEvent.id.asc())
            ).scalars()
        )
        if event not in scoring_events:
            scoring_events.append(event)  # last element supplies evidence_head

        trust_data = TrustPolicyV1.calculate_trust(scoring_events)
        
        snapshot = agent.trust_snapshot
        if not snapshot:
            snapshot = models.AgentTrustSnapshot(agent_id=agent.id)
            self.db.add(snapshot)
            agent.trust_snapshot = snapshot
        
        snapshot.trust_score = trust_data["trust_score"]
        snapshot.risk_tier = trust_data["risk_tier"]
        snapshot.trust_policy_version = trust_data["trust_policy_version"]
        snapshot.evidence_head = trust_data["evidence_head"]
        snapshot.calculated_at = utc_now()

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
                        created_at=existing.created_at,
                        persisted=True,
                        idempotent_replay=True,
                        chain_head=existing.event_hash,
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
            created_at=event.created_at,
            persisted=True,
            idempotent_replay=False,
            chain_head=event.event_hash,
        )

    def get_agent_history(
        self,
        agent_id: str,
        limit: int = 100,
        cursor: int | None = None,
        account_id: int | None = None,
    ) -> list[LedgerEventResponse]:
        agent = self._resolve_agent(agent_id, account_id)

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
                created_at=e.created_at,
            )
            for e in events
        ]

    def verify_chain(
        self, agent_id: str, *, account_id: int | None = None
    ) -> tuple[bool, dict[str, object]]:
        agent = self._resolve_agent(agent_id, account_id)

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

        if not events:
            return (
                False,
                {
                    "status": "unmeasured",
                    "valid": None,
                    "checked_events": 0,
                    "first_event_at": None,
                    "last_event_at": None,
                    "latest_event_hash": None,
                    "errors": [],
                    "reason": "No ledger events have been recorded for this agent.",
                },
            )

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
                "status": "verified" if not errors else "blocked",
                "valid": len(errors) == 0,
                "checked_events": len(events),
                "first_event_at": first_event_at,
                "last_event_at": last_event_at,
                "latest_event_hash": latest_hash,
                "errors": errors,
                "reason": (
                    "Ledger chain verified." if not errors else "Ledger chain verification failed."
                ),
            },
        )

    def get_event_by_hash(self, event_hash: str) -> LedgerEventResponse:
        event = self.db.execute(
            select(models.LedgerEvent).where(models.LedgerEvent.event_hash == event_hash)
        ).scalar_one_or_none()
        
        if not event:
            raise ValueError("Event not found")
            
        return LedgerEventResponse(
            event_id=event.event_id,
            event_type=event.event_type,
            actor=event.actor,
            summary=event.summary,
            details=event.details,
            prev_event_hash=event.prev_event_hash,
            event_hash=event.event_hash,
            created_at=event.created_at,
            persisted=True,
            idempotent_replay=False,
            chain_head=event.event_hash
        )

    def get_event_by_id(self, event_id: str, *, account_id: int) -> LedgerEventResponse:
        event = self.db.execute(
            select(models.LedgerEvent)
            .join(models.Agent, models.LedgerEvent.agent_id == models.Agent.id)
            .where(
                models.LedgerEvent.event_id == event_id,
                models.Agent.account_id == account_id,
            )
        ).scalar_one_or_none()
        if not event:
            raise ValueError("Event not found")
        chain_head = self.db.execute(
            select(models.LedgerEvent.event_hash)
            .where(models.LedgerEvent.agent_id == event.agent_id)
            .order_by(models.LedgerEvent.created_at.desc(), models.LedgerEvent.id.desc())
            .limit(1)
        ).scalar_one()
        return LedgerEventResponse(
            event_id=event.event_id,
            event_type=event.event_type,
            actor=event.actor,
            summary=event.summary,
            details=event.details,
            prev_event_hash=event.prev_event_hash,
            event_hash=event.event_hash,
            created_at=event.created_at,
            persisted=True,
            idempotent_replay=False,
            chain_head=chain_head,
        )
