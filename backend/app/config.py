from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Project Genome Ledger"
    environment: Literal["dev", "staging", "prod"] = "dev"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/pgl"
    redis_url: str = "redis://localhost:6379/0"

    stripe_api_key: str = "sk_test_placeholder"
    stripe_webhook_secret: str = "whsec_placeholder"

    auth_domain: str = "https://pgl.auth0.com/"
    auth_audience: str = "https://api.pgl.ai"

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
