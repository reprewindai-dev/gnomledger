"""Route contract: the documented /api/v1/admin, /agents and /billing paths resolve, the
legacy unprefixed mounts still work, and the legacy GET /api/v1/{agent_id} catch-all no
longer shadows GET /api/v1/usage or GET /api/v1/capabilities.

Audit (2026-10-06): agents, admin and billing were mounted without a prefix, so agents
lived at POST /api/v1/ and GET /api/v1/{agent_id}, while the README, the bundled UI and the
CAPPO client call /api/v1/agents/...; and because the agents router was mounted first, its
catch-all answered 404 "Unknown agent_id" for /api/v1/usage and /api/v1/capabilities.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import models
from app.dependencies import get_db
from app.main import create_app
from app.schemas import AgentCreateRequest, ApiKeyCreateRequest, GenomePayload
from app.services.certificate_service import CertificateService
from app.services.key_service import ApiKeyService
from app.utils import short_id

GENOME = {
    "model_family": "transformer",
    "model_version": "1",
    "architecture": "small",
    "tools": [],
    "permissions": ["read"],
    "safety_rules": ["none"],
    "runtime_config": {},
    "intended_use": "assist",
    "risk_category": "low",
}


@pytest.fixture
def world(session):
    account = models.Account(name=f"acct-{short_id('acc')}", tier="launch")
    session.add(account)
    session.flush()
    raw, _ = ApiKeyService(session).issue_api_key(
        account_id=account.id,
        payload=ApiKeyCreateRequest(name="operator", role="operator", scopes=["*"]),
    )
    agent = CertificateService(session).register_agent(
        AgentCreateRequest(
            agent_name="seed",
            creator="owner",
            jurisdiction="US",
            genome=GenomePayload(**GENOME),
            parent_agent_ids=[],
        ),
        account_id=account.id,
    )
    app = create_app()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return {"client": TestClient(app), "headers": {"x-api-key": raw}, "agent": agent}


def test_agent_detail_resolves_on_documented_and_legacy_paths(world):
    client, headers, agent = world["client"], world["headers"], world["agent"]

    documented = client.get(f"/api/v1/agents/{agent.agent_id}", headers=headers)
    legacy = client.get(f"/api/v1/{agent.agent_id}", headers=headers)

    assert documented.status_code == 200
    assert documented.json()["agent_id"] == agent.agent_id
    assert legacy.status_code == 200
    assert legacy.json() == documented.json()


def test_agent_collection_resolves_with_and_without_trailing_slash(world):
    client, headers = world["client"], world["headers"]

    for path in ("/api/v1/agents", "/api/v1/agents/", "/api/v1/"):
        response = client.get(path, headers=headers, follow_redirects=False)
        assert response.status_code == 200, path
        assert [a["agent_id"] for a in response.json()] == [world["agent"].agent_id], path

    body = {"agent_name": "second", "creator": "owner", "jurisdiction": "US", "genome": GENOME}
    created = client.post("/api/v1/agents", json=body, headers=headers, follow_redirects=False)
    assert created.status_code == 201
    assert created.json()["agent_id"].startswith("agent_")


def test_usage_and_capabilities_are_not_captured_by_agent_catch_all(world):
    client, headers = world["client"], world["headers"]

    for path in ("/api/v1/usage", "/api/v1/billing/usage"):
        response = client.get(path, headers=headers)
        assert response.status_code == 200, path
        assert isinstance(response.json(), list), path

    capabilities = client.get("/api/v1/capabilities")  # public discovery, no key
    assert capabilities.status_code == 200
    assert capabilities.json()["service"] == "gnomledger"


def test_openapi_lists_documented_paths_and_hides_legacy_mounts(world):
    schema = world["client"].get("/openapi.json")

    assert schema.status_code == 200
    paths = schema.json()["paths"]
    for documented in (
        "/api/v1/agents/",
        "/api/v1/agents/{agent_id}",
        "/api/v1/admin/bootstrap",
        "/api/v1/billing/usage",
        "/api/v1/capabilities",
    ):
        assert documented in paths, documented
    for legacy in ("/api/v1/", "/api/v1/{agent_id}", "/api/v1/bootstrap", "/api/v1/usage"):
        assert legacy not in paths, legacy


def test_admin_routes_resolve_under_documented_prefix(world):
    client = world["client"]
    body = {"bootstrap_token": "not-the-token", "account_name": "x", "admin_name": "a@x"}

    # Wrong token is 403 from the route itself; a 404/405 would mean the path did not resolve.
    assert client.post("/api/v1/admin/bootstrap", json=body).status_code == 403
    assert client.post("/api/v1/bootstrap", json=body).status_code == 403
