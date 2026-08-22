from __future__ import annotations

from pathlib import Path

from app import models
from app.schemas import AgentCreateRequest, GenomePayload, LedgerEventCreate
from app.services.certificate_service import CertificateService
from app.services.ledger_service import LedgerService
from app.services.lineage_service import LineageService
from app.utils import short_id


def test_vercel_python_runtime_matches_the_locked_project_version() -> None:
    repository_root = Path(__file__).resolve().parents[2]

    assert (repository_root / ".python-version").read_text(encoding="utf-8").strip() == "3.12"


def _seed_account(session, tier="launch"):
    account = models.Account(name=f"acct-{short_id('acc')}", tier=tier)
    session.add(account)
    session.flush()
    return account


def _seed_agent(session, account):
    payload = AgentCreateRequest(
        agent_name="seed",
        creator="owner",
        jurisdiction="US",
        genome=GenomePayload(
            model_family="transformer",
            model_version="1",
            architecture="small",
            tools=[],
            permissions=["read"],
            safety_rules=["none"],
            runtime_config={"gpu": "a10"},
            intended_use="assist",
            risk_category="low",
        ),
        parent_agent_ids=[],
    )
    return CertificateService(session).register_agent(payload, account_id=account.id)


def test_ledger_idempotency(session):
    account = _seed_account(session)
    created = _seed_agent(session, account)
    svc = LedgerService(session)
    event_payload = {
        "agent_id": created.agent_id,
        "event_type": "deployment",
        "actor": "owner",
        "summary": "deployed",
        "details": {"env": "prod"},
        "idempotency_key": "test-idempotent-1",
    }
    from app.schemas import LedgerEventCreate

    first = svc.log_event(LedgerEventCreate(**event_payload))
    second = svc.log_event(LedgerEventCreate(**event_payload))
    assert first.event_id == second.event_id


def test_exact_ledger_event_can_be_retrieved_by_id(session):
    account = _seed_account(session)
    created = _seed_agent(session, account)
    service = LedgerService(session)
    written = service.log_event(
        LedgerEventCreate(
            agent_id=created.agent_id,
            event_type="custom",
            actor="cappo-backend",
            summary="CAPPO evidence seal",
            details={"semantic_event_type": "capi_evidence_sealed", "evidence_seal": {"eee": {}}},
        )
    )

    retrieved = service.get_event_by_id(written.event_id, account_id=account.id)

    assert retrieved.event_id == written.event_id
    assert retrieved.event_hash == written.event_hash
    assert retrieved.persisted is True


def test_exact_ledger_event_is_scoped_to_its_account(session):
    owner = _seed_account(session)
    outsider = _seed_account(session)
    created = _seed_agent(session, owner)
    written = LedgerService(session).log_event(
        LedgerEventCreate(
            agent_id=created.agent_id,
            event_type="custom",
            actor="cappo-backend",
            summary="private evidence seal",
            details={"semantic_event_type": "capi_evidence_sealed"},
        )
    )

    import pytest

    with pytest.raises(ValueError, match="Event not found"):
        LedgerService(session).get_event_by_id(written.event_id, account_id=outsider.id)


def test_empty_ledger_is_unmeasured(session):
    account = _seed_account(session)
    created = _seed_agent(session, account)
    session.query(models.LedgerEvent).delete()
    session.commit()

    valid, result = LedgerService(session).verify_chain(created.agent_id)

    assert valid is False
    assert result["status"] == "unmeasured"
    assert result["valid"] is None
    assert result["checked_events"] == 0


def test_tampered_ledger_is_blocked(session):
    account = _seed_account(session)
    created = _seed_agent(session, account)
    event = LedgerService(session).log_event(
        LedgerEventCreate(
            agent_id=created.agent_id,
            event_type="deployment",
            actor="owner",
            summary="deployed",
            details={"env": "prod"},
        )
    )
    stored = session.query(models.LedgerEvent).filter_by(event_id=event.event_id).one()
    stored.details = {"env": "tampered"}
    session.commit()

    valid, result = LedgerService(session).verify_chain(created.agent_id)

    assert valid is False
    assert result["status"] == "blocked"
    assert result["valid"] is False


def test_lineage_fork_chain(session):
    account = _seed_account(session)
    created = _seed_agent(session, account)
    lineage = LineageService(session)
    forked = lineage.fork_agent(
        account_id=account.id,
        source_agent_id=created.agent_id,
        new_name="child",
        creator="owner",
        jurisdiction="US",
    )
    tree = lineage.get_tree(account.id, created.agent_id)
    assert tree.agent_id == created.agent_id
    assert len(tree.children) == 1
    assert tree.children[0].agent_id == forked.agent_id
