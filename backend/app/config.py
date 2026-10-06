from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _is_serverless_environment() -> bool:
    return bool(os.getenv("VERCEL"))


def _default_database_url() -> str:
    if _is_serverless_environment():
        return "sqlite:////tmp/pgl.sqlite3"
    return "sqlite:///./data/pgl.sqlite3"


def _default_certificate_storage_path() -> str:
    if _is_serverless_environment():
        return "/tmp/certificates"
    return "./data/certificates"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Project Genome Ledger"
    environment: Literal["dev", "staging", "prod"] = "dev"

    database_url: str = Field(default_factory=_default_database_url)
    redis_url: str = "redis://localhost:6379/0"

    stripe_api_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_event_retention_days: int = 30

    api_key_secret: str = "change-this-secret-in-prod"
    bootstrap_admin_token: str = "dev-bootstrap-token"
    pgl_ledger_api_key: str | None = Field(default=None, repr=False)
    bootstrap_account_name: str = "Veklom Capability OS"
    bootstrap_admin_name: str = "capability-os-runtime"

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    allow_anonymous_in_dev: bool = False
    cors_origins: list[str] = Field(default_factory=list)

    # --- Universal USB (cAPI) Integration ---
    capi_backend_url: str | None = "http://capi-container:3003"
    capi_api_key: str | None = None

    frontend_origin: str | None = None
    certificate_storage_path: str = Field(default_factory=_default_certificate_storage_path)
    # Ed25519 key that signs birth certificates, checkpoints and audit bundles. Required in
    # prod; in dev/staging a key is generated once under the data directory if both are unset.
    pgl_signing_key_pem: str | None = Field(default=None, repr=False)
    pgl_signing_key_path: str | None = None
    request_id_header: str = "x-request-id"

    @field_validator("environment")
    @classmethod
    def _normalize_env(cls, value: str) -> str:
        return value.lower().strip()

    @computed_field
    @property
    def is_local(self) -> bool:
        return self.environment == "dev"

    @field_validator("api_key_secret")
    @classmethod
    def _validate_api_key_secret(cls, value: str, info) -> str:
        environment = (info.data.get("environment") or "dev").lower()
        if environment == "prod" and value == "change-this-secret-in-prod":
            raise ValueError("api_key_secret must be overridden in production")
        minimum = 32 if environment == "prod" else 16
        if not value or len(value) < minimum:
            raise ValueError(f"api_key_secret must be at least {minimum} characters")
        return value

    @field_validator("pgl_ledger_api_key")
    @classmethod
    def _validate_runtime_api_key(cls, value: str | None, info) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        environment = (info.data.get("environment") or "dev").lower()
        minimum = 32 if environment == "prod" else 16
        if len(value) < minimum:
            raise ValueError(
                f"pgl_ledger_api_key must be at least {minimum} characters"
            )
        return value

    @field_validator("pgl_signing_key_pem", "pgl_signing_key_path")
    @classmethod
    def _blank_signing_key_is_unset(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value.strip()

    @model_validator(mode="after")
    def _require_signing_key_in_prod(self) -> "Settings":
        if self.environment != "prod":
            return self
        if not self.pgl_signing_key_pem and not self.pgl_signing_key_path:
            raise ValueError(
                "PGL_SIGNING_KEY_PEM or PGL_SIGNING_KEY_PATH must be set in production: the "
                "ledger signs birth certificates and checkpoints with this Ed25519 key"
            )
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        try:
            if self.pgl_signing_key_pem:
                pem = self.pgl_signing_key_pem.replace("\\n", "\n").encode("utf-8")
            else:
                pem = Path(self.pgl_signing_key_path).read_bytes()
            key = serialization.load_pem_private_key(pem, password=None)
        except (OSError, ValueError, TypeError) as exc:
            # The exception text is not echoed: it could quote key material.
            raise ValueError(f"PGL signing key could not be loaded ({type(exc).__name__})") from None
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("PGL signing key must be an Ed25519 private key")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
