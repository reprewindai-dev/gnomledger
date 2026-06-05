from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Project Genome Ledger"
    environment: Literal["dev", "staging", "prod"] = "dev"

    database_url: str = "sqlite:///./data/pgl.sqlite3"
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
    certificate_storage_path: str = "./data/certificates"
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
