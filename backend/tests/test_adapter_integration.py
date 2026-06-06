from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app import models
from app.dependencies import get_db
from app.schemas import AgentCreateRequest, ApiKeyCreateRequest, GenomePayload
from app.services.certificate_service import CertificateService
from app.services.key_service import ApiKeyService


def _bootstrap_account(session):
    account = models.Account(name="Adapter Demo", tier="launch")
    session.add(account)
    session.flush()
    return account


def _issue_agent(session, account):
    payload = AgentCreateRequest(
        agent_name="vekml-seed",
        creator="owner",
        jurisdiction="US",
        genome=GenomePayload(
            model_family="transformer",
            model_version="1",
            architecture="tool-using-agent",
            tools=["browser"],
            permissions=["read"],
            safety_rules=["review"],
            runtime_config={"temperature": 0.1},
            intended_use="integration",
            risk_category="low",
        ),
        parent_agent_ids=[],
    )
    return CertificateService(session).register_agent(payload, account_id=account.id)


def test_vekml_adapter_snapshot_returns_hardened_bundle(session):
    account = _bootstrap_account(session)
    raw_key, _ = ApiKeyService(session).issue_api_key(
        account_id=account.id,
        payload=ApiKeyCreateRequest(name="viewer", role="viewer", scopes=["*"], account_id=account.id),
    )
    created = _issue_agent(session, account)

    app = create_app()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    response = client.get(
        f"/api/v1/integrations/vekml/agents/{created.agent_id}/snapshot",
        headers={"x-api-key": raw_key},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["adapter"] == "vekml"
    assert body["agent"]["agent_id"] == created.agent_id
    assert body["certificate"]["certificate_id"] == created.certificate_id
    assert body["chain_verification"]["valid"] is True
    assert len(body["ledger_events"]) >= 1
    assert {row["metric"] for row in body["usage_limits"]} == {"certificate_issuance", "lineage_render"}
    assert body["snapshot_hash"]


def test_vekml_adapter_snapshot_respects_account_scope(session):
    account = _bootstrap_account(session)
    other = models.Account(name="Other Adapter Demo", tier="launch")
    session.add(other)
    session.flush()

    raw_key, _ = ApiKeyService(session).issue_api_key(
        account_id=account.id,
        payload=ApiKeyCreateRequest(name="viewer-scope", role="viewer", scopes=["*"], account_id=account.id),
    )
    created = _issue_agent(session, other)

    app = create_app()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    response = client.get(
        f"/api/v1/integrations/vekml/agents/{created.agent_id}/snapshot",
        headers={"x-api-key": raw_key},
    )
    assert response.status_code == 404
