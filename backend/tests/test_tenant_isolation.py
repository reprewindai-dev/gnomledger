"""Tenant isolation: a key from one account must not reach another account's agent.

Audit (2026-10-06) observed that ledger append/history/verify, genome update, execution
validate, incidents and reminders looked agents up by agent_id alone, so any authenticated
account could read, write or verify any other account's agent. Every foreign-agent call now
answers exactly like an unknown agent (404, or allowed=False for validate) so existence is
not leaked. The public proof route stays public by design.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import models
from app.dependencies import get_db
from app.main import create_app
from app.schemas import AgentCreateRequest, ApiKeyCreateRequest, GenomePayload, LedgerEventCreate
from app.services.certificate_service import CertificateService
from app.services.key_service import ApiKeyService
from app.services.ledger_service import LedgerService
from app.utils import short_id


def _account(session, tier="launch"):
    account = models.Account(name=f"acct-{short_id('acc')}", tier=tier)
    session.add(account)
    session.flush()
    return account


def _key(session, account, role="operator"):
    raw, _ = ApiKeyService(session).issue_api_key(
        account_id=account.id,
        payload=ApiKeyCreateRequest(name=f"{role}-{short_id('k')}", role=role, scopes=["*"]),
    )
    return {"x-api-key": raw}


def _agent(session, account):
    payload = AgentCreateRequest(
        agent_name="seed",
        creator="owner",
        jurisdiction="US",
        genome=GenomePayload(
            model_family="transformer",
            model_version="1",
            architecture="small",
            tools=["browser"],
            permissions=["read"],
            safety_rules=["none"],
            runtime_config={"gpu": "a10"},
            intended_use="assist",
            risk_category="low",
        ),
        parent_agent_ids=[],
    )
    return CertificateService(session).register_agent(payload, account_id=account.id)


@pytest.fixture
def tenants(session):
    owner = _account(session)
    outsider = _account(session)
    agent = _agent(session, owner)
    event = LedgerService(session).log_event(
        LedgerEventCreate(
            agent_id=agent.agent_id,
            event_type="deployment",
            actor="owner",
            summary="deployed",
            details={"env": "prod"},
        )
    )
    app = create_app()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return {
        "client": TestClient(app),
        "session": session,
        "agent": agent,
        "event": event,
        "owner_key": _key(session, owner),
        "owner_viewer_key": _key(session, owner, role="viewer"),
        "outsider_key": _key(session, outsider),
    }


def _ledger_event_body(agent_id: str) -> dict:
    return {
        "agent_id": agent_id,
        "event_type": "custom",
        "actor": "outsider",
        "summary": "cross-tenant write",
        "details": {},
    }


def test_outsider_cannot_append_to_foreign_agent_chain(tenants):
    client, agent = tenants["client"], tenants["agent"]
    body = _ledger_event_body(agent.agent_id)

    written = tenants["session"].query(models.LedgerEvent).filter_by(actor="outsider")

    assert client.post("/api/v1/ledger/events", json=body, headers=tenants["outsider_key"]).status_code == 404
    assert written.count() == 0

    assert client.post("/api/v1/ledger/events", json=body, headers=tenants["owner_key"]).status_code == 201
    assert written.count() == 1


def test_outsider_cannot_read_or_verify_foreign_agent_chain(tenants):
    client, agent = tenants["client"], tenants["agent"]
    history = f"/api/v1/ledger/agents/{agent.agent_id}"
    verify = f"{history}/verify"

    assert client.get(history, headers=tenants["outsider_key"]).status_code == 404
    assert client.get(verify, headers=tenants["outsider_key"]).status_code == 404

    owner_history = client.get(history, headers=tenants["owner_key"])
    assert owner_history.status_code == 200
    # registration logs birth_registration first, then the fixture's deployment event
    assert [e["event_type"] for e in owner_history.json()] == ["birth_registration", "deployment"]
    assert owner_history.json()[-1]["event_id"] == tenants["event"].event_id
    assert client.get(verify, headers=tenants["owner_key"]).json()["status"] == "verified"


def test_outsider_cannot_update_foreign_agent_genome(tenants):
    client, agent = tenants["client"], tenants["agent"]
    path = f"/api/v1/{agent.agent_id}/genome"
    body = {
        "actor": "outsider",
        "note": "cross-tenant mutation",
        "reason": "model upgrade",
        "changes": {
            "model_family": "transformer",
            "model_version": "2",
            "architecture": "small",
            "intended_use": "assist",
            "risk_category": "low",
        },
    }

    assert client.patch(path, json=body, headers=tenants["outsider_key"]).status_code == 404
    versions = tenants["session"].query(models.GenomeVersion).count()
    assert versions == 1

    assert client.patch(path, json=body, headers=tenants["owner_key"]).status_code == 200
    assert tenants["session"].query(models.GenomeVersion).count() == 2


def test_outsider_cannot_bind_workspace_through_execution_validate(tenants):
    client, agent, session = tenants["client"], tenants["agent"], tenants["session"]
    genome_hash = session.query(models.GenomeVersion).one().genome_hash
    body = {
        "agent_id": agent.agent_id,
        "workspace_id": "ws-outsider",
        "requested_tools": ["browser"],
        "expected_genome_hash": genome_hash,
    }

    response = client.post("/api/v1/execution/validate", json=body, headers=tenants["outsider_key"])
    assert response.status_code == 200
    assert response.json()["allowed"] is False
    assert response.json()["agent_certificate_id"] is None
    assert session.query(models.Agent).one().workspace_id is None

    body["workspace_id"] = "ws-owner"
    response = client.post("/api/v1/execution/validate", json=body, headers=tenants["owner_key"])
    assert response.json()["allowed"] is True
    session.expire_all()
    assert session.query(models.Agent).one().workspace_id == "ws-owner"


@pytest.mark.parametrize(
    ("resource", "body"),
    [
        (
            "incidents",
            {"severity": "low", "title": "t", "description": "d", "reporter": "r"},
        ),
        (
            "reminders",
            {
                "title": "t",
                "message": "m",
                "frequency": "once",
                "next_trigger_at": "2026-10-07T00:00:00Z",
            },
        ),
    ],
)
def test_incidents_and_reminders_are_account_scoped_and_role_checked(tenants, resource, body):
    client, agent = tenants["client"], tenants["agent"]
    path = f"/api/v1/agents/{agent.agent_id}/{resource}"

    assert client.post(path, json=body, headers=tenants["outsider_key"]).status_code == 404
    assert client.get(path, headers=tenants["outsider_key"]).status_code == 404
    assert client.post(path, json=body, headers=tenants["owner_viewer_key"]).status_code == 403

    created = client.post(path, json=body, headers=tenants["owner_key"])
    assert created.status_code == 201
    item_id = created.json()[f"{resource[:-1]}_id"]

    assert client.get(f"{path}/{item_id}", headers=tenants["outsider_key"]).status_code == 404
    assert client.delete(f"{path}/{item_id}", headers=tenants["outsider_key"]).status_code == 404
    assert client.get(f"{path}/{item_id}", headers=tenants["owner_viewer_key"]).status_code == 200
    assert client.delete(f"{path}/{item_id}", headers=tenants["owner_viewer_key"]).status_code == 403
    assert client.delete(f"{path}/{item_id}", headers=tenants["owner_key"]).status_code == 204


def test_public_proof_route_stays_public(tenants):
    response = tenants["client"].get(f"/api/v1/ledger/proof/{tenants['event'].event_hash}")

    assert response.status_code == 200
    assert response.json()["event_hash"] == tenants["event"].event_hash
