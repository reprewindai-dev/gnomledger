from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings
from ..utils import hash_api_key, utc_now


RUNTIME_KEY_NAME = "capability-os-runtime"


def ensure_runtime_bootstrap(db: Session, settings: Settings) -> bool:
    """Create or verify the single configured Capability OS runtime principal.

    The raw key is supplied by deployment configuration and is never generated,
    returned, or logged here. An empty database may be initialized exactly once.
    Once any account exists, a missing or mismatched configured key fails closed
    instead of silently rotating authority.

    Returns ``True`` only when a new account/key pair was created.
    """

    raw_key = settings.pgl_ledger_api_key
    account_count = db.scalar(select(func.count()).select_from(models.Account)) or 0
    key_count = db.scalar(select(func.count()).select_from(models.ApiKey)) or 0

    if not raw_key:
        if account_count or key_count:
            raise RuntimeError(
                "PGL_LEDGER_API_KEY is required to verify the configured runtime principal"
            )
        if settings.environment == "prod":
            raise RuntimeError("PGL_LEDGER_API_KEY is required for production bootstrap")
        return False

    configured_hash = hash_api_key(raw_key)
    existing_key = db.execute(
        select(models.ApiKey).where(models.ApiKey.key_hash == configured_hash)
    ).scalar_one_or_none()

    if existing_key is not None:
        if existing_key.revoked_at is not None:
            raise RuntimeError("Configured PGL runtime key is revoked")
        return False

    if account_count or key_count:
        raise RuntimeError(
            "Configured PGL runtime key does not match the initialized database"
        )

    try:
        account = models.Account(
            name=settings.bootstrap_account_name,
            tier="enterprise",
            status="active",
        )
        db.add(account)
        db.flush()
        db.add(
            models.User(
                account_id=account.id,
                email=settings.bootstrap_admin_name,
                role="owner",
                is_active=True,
            )
        )
        db.add(
            models.ApiKey(
                account_id=account.id,
                name=RUNTIME_KEY_NAME,
                key_prefix=raw_key[:12],
                key_hash=configured_hash,
                role="owner",
                scopes=["*"],
                expires_at=None,
                revoked_at=None,
                created_at=utc_now(),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True
