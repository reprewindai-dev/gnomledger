"""Who did it, from the authentication context rather than from a field the caller types."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .. import models
from ..schemas import PGLRequestContext


def describe_principal(db: Session, ctx: PGLRequestContext) -> dict[str, Any]:
    key = db.get(models.ApiKey, ctx.api_key_id)
    return {
        "type": "api_key",
        "account_id": ctx.account_id,
        "api_key_id": ctx.api_key_id,
        "api_key_name": key.name if key else None,
        "api_key_prefix": key.key_prefix if key else None,  # display prefix, not the secret
        "role": ctx.role,
    }


def principal_label(principal: dict[str, Any] | None) -> str:
    if not principal:
        return "system"
    return f"api_key:{principal['api_key_id']}:{principal.get('api_key_name') or ''}"[:255]
