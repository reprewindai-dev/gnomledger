from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal
from .models import Account, ApiKey
from .schemas import PGLRequestContext
from .utils import hash_api_key


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _account_from_token(db: Session, api_key: str) -> PGLRequestContext:
    settings = get_settings()
    if not api_key:
        if settings.allow_anonymous_in_dev and settings.environment == "dev":
            account = db.execute(select(Account).where(Account.tier == "launch")).scalar_one_or_none()
            if not account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No account in development database. Seed with bootstrap first.",
                )
            key = db.execute(
                select(ApiKey).where(ApiKey.account_id == account.id).limit(1)
            ).scalar_one_or_none()
            if not key:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="No API keys configured",
                )
            return PGLRequestContext(account_id=account.id, api_key_id=key.id, role=key.role)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    candidate_hash = hash_api_key(api_key)
    row = db.execute(select(ApiKey).where(ApiKey.key_hash == candidate_hash)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    now = datetime.now(timezone.utc)
    if row.expires_at and row.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key expired")
    if row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API key revoked")

    row.last_used_at = now
    db.commit()
    return PGLRequestContext(account_id=row.account_id, api_key_id=row.id, role=row.role)


def auth_context(
    x_api_key: Annotated[str | None, Header(alias="x-api-key")] = None,
    db: Session = Depends(get_db),
) -> PGLRequestContext:
    return _account_from_token(db, x_api_key)


ROLE_RANK = {"viewer": 1, "operator": 2, "admin": 3, "owner": 4}


def require_role(*roles: str) -> Callable[[PGLRequestContext], PGLRequestContext]:
    def _require(ctx: Annotated[PGLRequestContext, Depends(auth_context)]) -> PGLRequestContext:
        if not roles:
            return ctx

        if ctx.role not in ROLE_RANK:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid role configured for API key",
            )
        if any(role == "any" for role in roles):
            return ctx

        unknown_roles = [r for r in roles if r != "any" and r not in ROLE_RANK]
        if unknown_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid role policy configured for endpoint: {', '.join(unknown_roles)}",
            )

        valid_role_ranks = [ROLE_RANK[r] for r in roles if r in ROLE_RANK]
        if not valid_role_ranks:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid role policy configured for endpoint",
            )

        # `roles` is an allowlist with RBAC hierarchy support:
        # allow if caller has sufficient rank for the least-privileged
        # requested role in that allowlist.
        required_rank = min(valid_role_ranks)
        if ROLE_RANK.get(ctx.role, 0) < required_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role for this action",
            )
        return ctx

    return _require


def db_dependency() -> Session:
    return Depends(get_db)
