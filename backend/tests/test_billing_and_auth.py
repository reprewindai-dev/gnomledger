from __future__ import annotations

from fastapi import HTTPException
import pytest

from app import models
from app.dependencies import require_role
from app.schemas import AgentCreateRequest, ApiKeyCreateRequest, GenomePayload, PGLRequestContext
from app.services.certificate_service import CertificateService
from app.services.key_service import ApiKeyService
from app.services.billing_service import PLAN_QUOTAS
from app.utils import hash_api_key


def _bootstrap_account(session):
    account = models.Account(name="Demo", tier="launch")
    session.add(account)
    session.flush()
    return account


def test_api_key_hash_verification_and_lookup(session):
    account = _bootstrap_account(session)
    raw, key = ApiKeyService(session).issue_api_key(
        account_id=account.id,
        payload=ApiKeyCreateRequest(name="owner", role="owner", scopes=["*"], account_id=account.id),
    )
    assert raw.startswith("pgl_")
    assert hash_api_key(raw) == key.key_hash


def test_certificate_quota_blocks_beyond_plan(session):
    account = models.Account(name="Quota", tier="launch")
    session.add(account)
    session.flush()

    # raise limits down for determinism
    old_limit = PLAN_QUOTAS["launch"]["certificate_issuance"]
    PLAN_QUOTAS["launch"]["certificate_issuance"] = 1
    try:
        service = CertificateService(session)
        payload = AgentCreateRequest(
            agent_name="alpha",
            creator="owner",
            jurisdiction="US",
            genome=GenomePayload(
                model_family="x",
                model_version="1",
                architecture="y",
                tools=[],
                permissions=[],
                safety_rules=[],
                runtime_config={},
                intended_use="demo",
                risk_category="low",
            ),
            parent_agent_ids=[],
        )
        service.register_agent(payload, account_id=account.id)

        # second issuance should fail
        try:
            service.register_agent(payload, account_id=account.id)
            assert False, "Expected quota exception"
        except ValueError as exc:
            assert "quota" in str(exc).lower()
    finally:
        PLAN_QUOTAS["launch"]["certificate_issuance"] = old_limit


def test_require_role_minimum_rank():
    allowed_for_admin = require_role("admin", "owner")
    allowed_for_all = require_role("viewer", "operator", "admin", "owner")

    allowed_for_admin(PGLRequestContext(account_id=1, api_key_id=1, role="owner"))
    allowed_for_admin(PGLRequestContext(account_id=1, api_key_id=1, role="admin"))

    allowed_for_all(PGLRequestContext(account_id=1, api_key_id=1, role="viewer"))
    allowed_for_all(PGLRequestContext(account_id=1, api_key_id=1, role="operator"))
    allowed_for_all(PGLRequestContext(account_id=1, api_key_id=1, role="admin"))

    with pytest.raises(HTTPException) as exc:
        allowed_for_admin(PGLRequestContext(account_id=1, api_key_id=1, role="viewer"))
    assert exc.value.status_code == 403


def test_api_key_rejects_invalid_role(session):
    account = _bootstrap_account(session)
    with pytest.raises(ValueError):
        ApiKeyService(session).issue_api_key(
            account_id=account.id,
            payload=ApiKeyCreateRequest(name="invalid", role="hacker", scopes=["*"]),
        )


def test_api_key_name_must_be_unique_within_account(session):
    account = _bootstrap_account(session)
    service = ApiKeyService(session)
    service.issue_api_key(account_id=account.id, payload=ApiKeyCreateRequest(name="dup", role="owner", scopes=["*"]))
    with pytest.raises(ValueError):
        service.issue_api_key(account_id=account.id, payload=ApiKeyCreateRequest(name="dup", role="admin", scopes=["*"]))
