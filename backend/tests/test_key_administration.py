"""Key administration: admins manage their own account's keys only, and nobody mints a key
above their own role.

Audit (2026-10-06): POST/GET/DELETE /accounts/{account_id}/keys accepted any admin for any
account_id, the request body could redirect the new key to another account, and an admin
could mint an owner key. Owners keep cross-account administration.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import models
from app.dependencies import get_db
from app.main import create_app
from app.schemas import ApiKeyCreateRequest
from app.services.key_service import ApiKeyService
from app.utils import short_id


def _account(session):
    account = models.Account(name=f"acct-{short_id('acc')}", tier="launch")
    session.add(account)
    session.flush()
    return account


def _key(session, account, role):
    raw, key = ApiKeyService(session).issue_api_key(
        account_id=account.id,
        payload=ApiKeyCreateRequest(name=f"{role}-{short_id('k')}", role=role, scopes=["*"]),
    )
    return {"x-api-key": raw}, key


@pytest.fixture
def world(session):
    mine, theirs = _account(session), _account(session)
    owner_headers, _ = _key(session, mine, "owner")
    admin_headers, _ = _key(session, mine, "admin")
    _, their_key = _key(session, theirs, "admin")
    app = create_app()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return {
        "client": TestClient(app),
        "session": session,
        "mine": mine,
        "theirs": theirs,
        "their_key": their_key,
        "owner": owner_headers,
        "admin": admin_headers,
    }


def _body(role: str, **extra) -> dict:
    return {"name": f"{role}-{short_id('n')}", "role": role, "scopes": ["*"], **extra}


def test_admin_cannot_administer_another_accounts_keys(world):
    client, theirs, their_key = world["client"], world["theirs"], world["their_key"]
    base = f"/api/v1/accounts/{theirs.id}/keys"

    assert client.post(base, json=_body("viewer"), headers=world["admin"]).status_code == 404
    assert client.get(base, headers=world["admin"]).status_code == 404
    assert client.delete(f"{base}/{their_key.id}", headers=world["admin"]).status_code == 404

    world["session"].refresh(their_key)
    assert their_key.revoked_at is None
    assert world["session"].query(models.ApiKey).filter_by(account_id=theirs.id).count() == 1


def test_admin_body_cannot_redirect_key_to_another_account(world):
    client, mine, theirs = world["client"], world["mine"], world["theirs"]

    response = client.post(
        f"/api/v1/accounts/{mine.id}/keys",
        json=_body("viewer", account_id=theirs.id),
        headers=world["admin"],
    )

    assert response.status_code == 400
    assert world["session"].query(models.ApiKey).filter_by(account_id=theirs.id).count() == 1


def test_admin_cannot_mint_owner_key_but_can_mint_admin_key(world):
    client, mine = world["client"], world["mine"]
    base = f"/api/v1/accounts/{mine.id}/keys"

    assert client.post(base, json=_body("owner"), headers=world["admin"]).status_code == 403
    assert world["session"].query(models.ApiKey).filter_by(account_id=mine.id, role="owner").count() == 1

    response = client.post(base, json=_body("admin"), headers=world["admin"])
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.json()["account_id"] == mine.id


def test_admin_manages_own_account_keys(world):
    client, mine = world["client"], world["mine"]
    base = f"/api/v1/accounts/{mine.id}/keys"

    listed = client.get(base, headers=world["admin"])
    assert listed.status_code == 200
    minted = client.post(base, json=_body("viewer"), headers=world["admin"]).json()
    key_id = next(k["id"] for k in client.get(base, headers=world["admin"]).json() if k["key_prefix"] == minted["api_key_prefix"])

    assert client.delete(f"{base}/{key_id}", headers=world["admin"]).status_code == 204
    # the revoked key is rejected by auth (dependencies.py: revoked -> 403)
    assert client.get("/api/v1/", headers={"x-api-key": minted["api_key"]}).status_code == 403


def test_owner_keeps_cross_account_administration(world):
    client, theirs = world["client"], world["theirs"]
    base = f"/api/v1/accounts/{theirs.id}/keys"

    response = client.post(base, json=_body("owner"), headers=world["owner"])

    assert response.status_code == 200
    assert response.json()["account_id"] == theirs.id
    assert client.get(base, headers=world["owner"]).status_code == 200


def test_service_refuses_role_above_issuer(session):
    account = _account(session)

    with pytest.raises(PermissionError):
        ApiKeyService(session).issue_api_key(
            account_id=account.id,
            payload=ApiKeyCreateRequest(name="escalate", role="owner", scopes=["*"]),
            issuer_role="admin",
        )
    # Internal callers (bootstrap) pass no issuer_role and are unaffected.
    _, key = ApiKeyService(session).issue_api_key(
        account_id=account.id,
        payload=ApiKeyCreateRequest(name="bootstrap", role="owner", scopes=["*"]),
    )
    assert key.role == "owner"
