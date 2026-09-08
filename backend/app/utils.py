from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from .config import get_settings


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def canonical_timestamp(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.isoformat(timespec="microseconds")


def stable_hash(data: dict[str, Any]) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def short_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def hash_api_key(raw_key: str) -> str:
    settings = get_settings()
    digest = hmac.new(
        settings.api_key_secret.encode("utf-8"),
        msg=raw_key.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return digest
