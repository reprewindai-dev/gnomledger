"""On Vercel only /tmp is writable and it is wiped when an instance recycles, so a production
ledger must not fall back to its default SQLite file there."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.signing_service import generate_private_key_pem

PROD = {
    "environment": "prod",
    "api_key_secret": "serverless-test-secret-that-is-at-least-32-characters",
    "bootstrap_admin_token": "bootstrap-admin-test-secret",
}


def test_production_on_vercel_refuses_the_ephemeral_sqlite_default(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="DATABASE_URL must point to Postgres"):
        Settings(**PROD, pgl_signing_key_pem=generate_private_key_pem())


def test_production_on_vercel_accepts_postgres(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    settings = Settings(
        **PROD,
        pgl_signing_key_pem=generate_private_key_pem(),
        database_url="postgresql://pgl:secret@db.example.neon.tech/pgl?sslmode=require",
    )
    assert settings.database_url.startswith("postgresql://")


def test_preview_and_dev_on_vercel_may_use_sqlite(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    assert Settings(environment="dev").database_url.startswith("sqlite")
