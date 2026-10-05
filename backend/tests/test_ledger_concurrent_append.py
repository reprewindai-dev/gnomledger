"""Regression: concurrent appends must not fork an agent's hash chain.

Lineage-reformation run lre-20261005T001846Z: two CAPPO requests appended to the same
agent ~100 ms apart, both read the same chain head, and verify returned "blocked"
(event_hash mismatch / chain break). Appends are now serialized on the agent row.

Needs a real Postgres (row locks); set PGL_TEST_POSTGRES_URL to run it. SQLite ignores
FOR UPDATE, so the sequential tests cover that backend.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.schemas import AgentCreateRequest, LedgerEventCreate
from app.services.certificate_service import CertificateService
from app.services.ledger_service import LedgerService

POSTGRES_URL = os.environ.get("PGL_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="PGL_TEST_POSTGRES_URL not set")

WRITERS = 8
APPENDS_PER_WRITER = 25


def test_concurrent_appends_keep_one_chain() -> None:
    engine = create_engine(POSTGRES_URL, pool_size=WRITERS + 2, future=True)
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    try:
        with Session() as db:
            account = models.Account(name="concurrency", tier="enterprise", status="active")
            db.add(account)
            db.commit()
            agent = CertificateService(db).register_agent(
                AgentCreateRequest(
                    agent_name="concurrent-writer",
                    creator="test",
                    jurisdiction="US",
                    genome={
                        "model_family": "m", "model_version": "1", "architecture": "a",
                        "intended_use": "concurrency regression", "risk_category": "low",
                    },
                ),
                account_id=account.id,
            )
            agent_id = agent.agent_id

        def writer(w: int) -> None:
            with Session() as db:
                svc = LedgerService(db)
                for i in range(APPENDS_PER_WRITER):
                    svc.log_event(LedgerEventCreate(
                        agent_id=agent_id, event_type="custom", actor=f"writer-{w}",
                        summary="concurrent append", details={"w": w, "i": i},
                        idempotency_key=f"w{w}-i{i}",
                    ))

        with ThreadPoolExecutor(WRITERS) as pool:
            for f in [pool.submit(writer, w) for w in range(WRITERS)]:
                f.result()

        with Session() as db:
            valid, report = LedgerService(db).verify_chain(agent_id)
            events = db.query(models.LedgerEvent).all()
        expected = WRITERS * APPENDS_PER_WRITER + 1  # + birth_registration
        assert report["checked_events"] == expected
        assert report["errors"] == []
        assert valid is True
        prev_hashes = [e.prev_event_hash for e in events]
        assert len(set(prev_hashes)) == len(prev_hashes), "two events share a previous hash (fork)"
    finally:
        models.Base.metadata.drop_all(bind=engine)
        engine.dispose()
