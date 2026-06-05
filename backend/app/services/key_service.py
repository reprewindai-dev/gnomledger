from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..schemas import ApiKeyCreateRequest
from ..utils import hash_api_key, utc_now


class ApiKeyService:
    def __init__(self, db: Session):
        self.db = db

    def issue_api_key(
        self,
        account_id: int,
        payload: ApiKeyCreateRequest,
    ) -> tuple[str, models.ApiKey]:
        allowed_roles = {"viewer", "operator", "admin", "owner"}
        if payload.role not in allowed_roles:
            raise ValueError(f"Unsupported API key role: {payload.role}")
        if payload.account_id is not None:
            account_id = payload.account_id
        account = self.db.execute(
            select(models.Account).where(models.Account.id == account_id)
        ).scalar_one_or_none()
        if not account:
            raise ValueError("Unknown account_id")

        raw_key = f"pgl_{secrets.token_urlsafe(28)}"
        key_hash = hash_api_key(raw_key)
        key_prefix = raw_key[:12]

        key = models.ApiKey(
            account_id=account.id,
            name=payload.name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            role=payload.role,
            scopes=payload.scopes,
            expires_at=None,
            revoked_at=None,
            created_at=utc_now(),
        )
        self.db.add(key)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ValueError("A key with this name already exists for the account") from exc
        self.db.refresh(key)
        return raw_key, key

    def list_api_keys(self, account_id: int) -> list[models.ApiKey]:
        return list(
            self.db.execute(
                select(models.ApiKey).where(models.ApiKey.account_id == account_id).order_by(models.ApiKey.id.asc())
            ).scalars()
        )

    def revoke_api_key(self, account_id: int, api_key_id: int) -> None:
        key = self.db.execute(
            select(models.ApiKey).where(models.ApiKey.id == api_key_id, models.ApiKey.account_id == account_id)
        ).scalar_one_or_none()
        if not key:
            raise ValueError("Unknown API key")
        key.revoked_at = datetime.utcnow()
        self.db.commit()
