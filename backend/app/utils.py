from __future__ import annotations  # noqa: I001

import json
import uuid
from datetime import datetime, timezone
import hashlib
import hmac
from typing import Any, Dict  # noqa: UP035
from .config import get_settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017


def utc_now_iso() -> str:
    return utc_now().isoformat()


def canonical_timestamp(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)  # noqa: UP017
    return dt.isoformat(timespec="microseconds")


def stable_hash(data: Dict[str, Any]) -> str:  # noqa: UP006
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
