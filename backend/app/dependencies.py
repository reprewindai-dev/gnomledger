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


def get_current_account(
    ctx: Annotated[PGLRequestContext, Depends(auth_context)],
    db: Session = Depends(get_db),
) -> Account:
    """
    Was imported by routes/notary.py but never defined anywhere in this file —
    a pre-existing gap in the repo, unrelated to x402. Added here rather than
    left broken; the app could not previously boot with notary.py wired in.
    """
    account = db.execute(select(Account).where(Account.id == ctx.account_id)).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


# ---------------------------------------------------------------------------
# x402: pay-per-call access as an alternative to an API key/subscription.
# ---------------------------------------------------------------------------

import httpx  # noqa: E402

from .services.x402_service import get_price  # noqa: E402


async def _verify_x402_payment(payment_header: str, resource: str, method: str) -> bool:
    """
    Verifies an X-PAYMENT header against the configured x402 facilitator.
    Returns True only on confirmed, settled payment. Fails closed on any
    error, misconfiguration, or facilitator rejection — never assume payment
    succeeded.
    """
    settings = get_settings()
    if not settings.x402_enabled or not settings.x402_facilitator_url or not settings.x402_pay_to_address:
        # Real deployment blocker: x402 is wired but not turned on until
        # these are set. Fail closed rather than silently accepting requests.
        return False

    price = get_price(resource, method)
    if price is None:
        return False

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{settings.x402_facilitator_url.rstrip('/')}/verify",
                json={"paymentHeader": payment_header, "resource": resource, "method": method},
            )
            resp.raise_for_status()
            result = resp.json()
        except (httpx.HTTPError, ValueError):
            return False

    return bool(result.get("isValid"))


def require_apikey_or_x402(resource: str, method: str) -> Callable[..., PGLRequestContext]:
    """
    Allows either a valid x-api-key (subscription path) OR a valid X-PAYMENT
    header (pay-per-call x402 path, no account required). Use on endpoints
    listed in x402_service.PRICING. Endpoints not in that pricing table
    should keep using auth_context/require_role directly — this dependency
    is only for the specific priced resources.
    """

    async def _check(
        x_api_key: Annotated[str | None, Header(alias="x-api-key")] = None,
        x_payment: Annotated[str | None, Header(alias="x-payment")] = None,
        db: Session = Depends(get_db),
    ) -> PGLRequestContext:
        if x_api_key:
            return _account_from_token(db, x_api_key)

        if x_payment:
            paid = await _verify_x402_payment(x_payment, resource, method)
            if paid:
                # Pay-per-call callers get an ephemeral, unattributed context —
                # no account, no stored key, just proof-of-payment for this call.
                return PGLRequestContext(account_id=0, api_key_id=0, role="operator")
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Payment verification failed")

        price = get_price(resource, method)
        manifest_hint = {"price_usdc": str(price.price_usdc)} if price else {}
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "message": "Provide x-api-key (subscription) or x-payment (x402 pay-per-call)",
                "discovery": "/.well-known/x402",
                **manifest_hint,
            },
        )

    return _check
