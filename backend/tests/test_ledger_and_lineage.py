from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import models
from app.dependencies import get_db
from app.main import create_app
from app.schemas import AgentCreateRequest, ApiKeyCreateRequest, GenomePayload, LedgerEventCreate
from app.services.certificate_service import CertificateService
from app.services.key_service import ApiKeyService
from app.services.ledger_service import LedgerService
from app.services.lineage_service import LineageService
from app.utils import short_id


def test_vercel_python_runtime_matches_the_locked_project_version() -> None:
    repository_root = Path(__file__).resolve().parents[2]

    assert (repository_root / ".python-version").read_text(encoding="utf-8").strip() == "3.12"


def test_vercel_uses_the_database_driver_selected_by_runtime_code() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    requirements = (repository_root / "requirements.txt").read_text(encoding="utf-8")
    project = (repository_root / "pyproject.toml").read_text(encoding="utf-8")

    assert "psycopg[binary]==3.3.4" in requirements
    assert '"psycopg[binary]==3.3.4"' in project
    assert "psycopg2-binary" not in requirements
    assert "psycopg2-binary" not in project


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
    latest = service.log_event(
        LedgerEventCreate(
            agent_id=created.agent_id,
            event_type="custom",
            actor="cappo-backend",
            summary="later event",
            details={"semantic_event_type": "later"},
        )
    )

    retrieved = service.get_event_by_id(written.event_id, account_id=account.id)

    assert retrieved.event_id == written.event_id
    assert retrieved.event_hash == written.event_hash
    assert retrieved.persisted is True
    assert retrieved.chain_head == latest.event_hash


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


def test_exact_event_route_requires_auth_and_preserves_account_scoped_chain_contract(session):
    owner = _seed_account(session)
    outsider = _seed_account(session)
    owner_key, _ = ApiKeyService(session).issue_api_key(
        account_id=owner.id,
        payload=ApiKeyCreateRequest(name="cappo-service", role="viewer", scopes=["*"]),
    )
    outsider_key, _ = ApiKeyService(session).issue_api_key(
        account_id=outsider.id,
        payload=ApiKeyCreateRequest(name="outsider", role="viewer", scopes=["*"]),
    )
    created = _seed_agent(session, owner)
    written = LedgerService(session).log_event(
        LedgerEventCreate(
            agent_id=created.agent_id,
            event_type="custom",
            actor="cappo-backend",
            summary="sealed EEE",
            details={"semantic_event_type": "capi_evidence_sealed", "evidence_seal": {"eee": {}}},
        )
    )
    app = create_app()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    path = f"/api/v1/ledger/events/{written.event_id}"

    assert client.get(path).status_code == 401
    assert client.get(path, headers={"x-api-key": outsider_key}).status_code == 404
    response = client.get(path, headers={"x-api-key": owner_key})

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == written.event_id
    assert body["event_hash"] == written.event_hash
    assert "prev_event_hash" in body
    assert body["persisted"] is True
    assert body["details"]["semantic_event_type"] == "capi_evidence_sealed"


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
