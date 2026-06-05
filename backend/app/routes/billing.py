from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import select

import stripe

from ..config import get_settings
from ..dependencies import get_db, require_role
from .. import models
from ..schemas import BillingUsageResponse, UsageLimitResponse
from ..services.billing_service import BillingService

router = APIRouter()
settings = get_settings()


def _to_usage_response(row):
    return BillingUsageResponse(
        metric=row.metric,
        amount=float(row.amount),
        period_start=row.period_start,
        period_end=row.period_end,
    )


@router.get("/usage", response_model=list[BillingUsageResponse])
def get_usage(
    db: Session = Depends(get_db),
    ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> list[BillingUsageResponse]:
    service = BillingService(db)
    usage = service.list_usage(ctx.account_id)
    return [_to_usage_response(u) for u in usage]


@router.get("/usage/{metric}/limit", response_model=UsageLimitResponse)
def usage_limit(
    metric: str,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> UsageLimitResponse:
    account = db.execute(select(models.Account).where(models.Account.id == ctx.account_id)).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    service = BillingService(db)
    used = service.get_current_metric(ctx.account_id, metric)
    limit = service.plan_limit(account=account, metric=metric)
    return UsageLimitResponse(
        account_id=ctx.account_id,
        metric=metric,
        used=used,
        limit=limit,
        remaining=max(0.0, limit - used),
    )


@router.post("/stripe/webhook", status_code=status.HTTP_202_ACCEPTED)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=400, detail="Stripe webhook secret is not configured")
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing stripe signature")
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature,
            secret=settings.stripe_webhook_secret,
        )
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(status_code=400, detail="Invalid stripe signature") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Malformed webhook payload: {exc}") from exc

    BillingService(db).record_stripe_event(
        event_id=event["id"],
        event_type=event["type"],
        payload={"id": event["id"], "type": event["type"], "data": event["data"]},
    )
    return {"received": True}
