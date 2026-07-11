from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field, field_validator
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

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    allow_anonymous_in_dev: bool = False
    cors_origins: list[str] = Field(default_factory=list)

    frontend_origin: str | None = None
    certificate_storage_path: str = Field(default_factory=_default_certificate_storage_path)
    request_id_header: str = "x-request-id"

    # x402 micropayments — pay-per-call access, no account/subscription required.
    # See https://x402.org for the protocol spec. FACILITATOR is the service
    # that verifies/settles USDC payments; Coinbase runs a public one, or you
    # can self-host. This must be set to a real facilitator URL before x402
    # payments will actually settle — until then, discovery works but payment
    # verification will fail closed (see dependencies.py).
    x402_enabled: bool = False
    x402_facilitator_url: str | None = "https://x402-facilitator.coinbase.com"
    x402_pay_to_address: str | None = "0xCC34553b4e6332ffb9C1b61E22436ACA53113D1d"  # wallet that receives payment, e.g. 0x3a74...
    x402_network: Literal["base", "base-sepolia"] = "base"
    x402_asset: str = "USDC"
    x402_pool_account_id: int | None = 99999999  # reserved account that holds anonymous pay-per-call agents; must be seeded via migration before x402 write endpoints work end-to-end

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
