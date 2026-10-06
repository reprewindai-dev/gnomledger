from __future__ import annotations

import pytest

from app import models
from app.config import Settings
from app.services.bootstrap_service import ensure_runtime_bootstrap
from app.services.signing_service import generate_private_key_pem


RUNTIME_KEY = "pgl_runtime_key_that_is_long_enough_for_prod_001"
SIGNING_KEY_PEM = generate_private_key_pem()  # prod settings refuse to load without one


def _settings(key: str | None = RUNTIME_KEY) -> Settings:
    return Settings(
        environment="prod",
        api_key_secret="bootstrap-test-secret-that-is-at-least-32-characters",
        bootstrap_admin_token="bootstrap-admin-test-secret",
        pgl_ledger_api_key=key,
        pgl_signing_key_pem=SIGNING_KEY_PEM,
    )


def test_empty_database_is_bootstrapped_once(session):
    settings = _settings()

    assert ensure_runtime_bootstrap(session, settings) is True
    assert ensure_runtime_bootstrap(session, settings) is False

    assert session.query(models.Account).count() == 1
    assert session.query(models.User).count() == 1
    keys = session.query(models.ApiKey).all()
    assert len(keys) == 1
    assert keys[0].role == "owner"
    assert keys[0].scopes == ["*"]
    assert RUNTIME_KEY not in keys[0].key_hash


def test_initialized_database_rejects_different_runtime_key(session):
    assert ensure_runtime_bootstrap(session, _settings()) is True

    with pytest.raises(RuntimeError, match="does not match"):
        ensure_runtime_bootstrap(
            session,
            _settings("pgl_different_key_that_is_long_enough_for_prod_002"),
        )

    assert session.query(models.Account).count() == 1
    assert session.query(models.ApiKey).count() == 1


def test_production_empty_database_rejects_missing_runtime_key(session):
    with pytest.raises(RuntimeError, match="required for production bootstrap"):
        ensure_runtime_bootstrap(session, _settings(None))

    assert session.query(models.Account).count() == 0
    assert session.query(models.ApiKey).count() == 0


def test_runtime_key_does_not_require_a_transport_prefix(session):
    unprefixed_key = "runtime-key-without-prefix-but-long-enough-003"
    assert ensure_runtime_bootstrap(session, _settings(unprefixed_key)) is True
    assert session.query(models.ApiKey).count() == 1
