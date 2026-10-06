"""Shared data and helpers for the audit-readiness tests (registration, certificates,
checkpoints, retention and the audit bundle)."""

from __future__ import annotations

import copy
import hashlib

from fastapi.testclient import TestClient

from app import models
from app.dependencies import get_db
from app.main import create_app
from app.schemas import ApiKeyCreateRequest
from app.services.key_service import ApiKeyService
from app.utils import short_id

# The genome shape clients sent before the accountability fields existed.
LEGACY_GENOME = {
    "model_family": "transformer",
    "model_version": "1",
    "architecture": "small",
    "tools": ["browser"],
    "permissions": ["read"],
    "safety_rules": ["none"],
    "runtime_config": {"gpu": "a10"},
    "intended_use": "assist",
    "risk_category": "low",
}

PROMPT_SHA256 = hashlib.sha256(b"You are a careful assistant.").hexdigest()

FULL_GENOME = {
    **LEGACY_GENOME,
    "accountable_owner": {
        "name": "Dana Reyes",
        "role": "Head of Claims Automation",
        "email": "dana.reyes@example.com",
        "organization": "Example Insurance Ltd",
    },
    "incident_contact": "https://example.com/security/incident",
    "deployer": "Example Insurance Ltd",
    "provider": "Example Insurance Ltd",
    "model_provider": "Anthropic",
    "model_identifier": "claude-opus-5-5",
    "out_of_scope_uses": ["final claim denial without human review"],
    "known_limitations": ["may misread handwritten forms"],
    "data_categories": ["financial", "personal"],
    "log_retention_days": 365,
    "regulatory_risk_class": "high_risk",
    "risk_rationale": "Annex III point 5(c): insurance pricing and claims for natural persons.",
    "oversight": {
        "stop_mechanism": "CAPPO terminate",
        "oversight_contact": "claims-oversight@example.com",
        "escalation_path": "on-call claims lead, then CRO",
    },
    "run_mode": "human_in_the_loop",
    "industry": "insurance",
    "capability_refs": ["veklom.governed-counter@v1"],
    "system_prompt_sha256": PROMPT_SHA256,
    "code_commit": "2e5b004",
    "image_digest": "ghcr.io/example/claims-agent@sha256:" + "a" * 64,
    "tool_versions": {"browser": "1.4.2"},
}


def genome(**overrides) -> dict:
    data = copy.deepcopy(FULL_GENOME)
    data.update(overrides)
    return data


def registration(genome_body: dict | None = None, **overrides) -> dict:
    body = {
        "agent_name": "claims-triage",
        "creator": "dana.reyes@example.com",
        "jurisdiction": "EU",
        "genome": copy.deepcopy(genome_body if genome_body is not None else FULL_GENOME),
    }
    body.update(overrides)
    return body


def _account(session):
    account = models.Account(name=f"acct-{short_id('acc')}", tier="enterprise")
    session.add(account)
    session.flush()
    return account


def _key(session, account, role):
    raw, _ = ApiKeyService(session).issue_api_key(
        account_id=account.id,
        payload=ApiKeyCreateRequest(name=f"{role}-{short_id('k')}", role=role, scopes=["*"]),
    )
    return {"x-api-key": raw}


def make_world(session) -> dict:
    owner = _account(session)
    outsider = _account(session)
    app = create_app()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return {
        "client": TestClient(app),
        "session": session,
        "account": owner,
        "operator": _key(session, owner, "operator"),
        "viewer": _key(session, owner, "viewer"),
        "admin": _key(session, owner, "admin"),
        "outsider": _key(session, outsider, "owner"),
    }


def register(world, body: dict | None = None) -> dict:
    response = world["client"].post(
        "/api/v1/agents", json=body or registration(), headers=world["operator"]
    )
    assert response.status_code == 201, response.text
    return response.json()
