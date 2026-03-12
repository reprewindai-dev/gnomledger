from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..dependencies import get_db
from ..schemas import BillingUsageResponse, StripeWebhookPayload
from ..services.billing_service import BillingService

router = APIRouter()
settings = get_settings()


def _verify_signature(signature: str | None) -> None:
    if not signature:
        raise HTTPException(status_code=400, detail="Missing stripe signature")
    # TODO: verify signature using stripe library and settings.stripe_webhook_secret


@router.get("/usage", response_model=list[BillingUsageResponse])
def get_usage(account_id: int, db: Session = Depends(get_db)) -> list[BillingUsageResponse]:
    service = BillingService(db)
    usage = service.list_usage(account_id)
    return [
        BillingUsageResponse(
            metric=u.metric,
            amount=float(u.amount),
            period_start=u.period_start,
            period_end=u.period_end,
        )
        for u in usage
    ]


@router.post("/stripe/webhook", status_code=status.HTTP_202_ACCEPTED)
async def stripe_webhook(
    payload: StripeWebhookPayload,
    stripe_signature: str | None = Header(default=None, alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    _verify_signature(stripe_signature)

    BillingService(db).record_stripe_event(
        event_id=payload.id,
        event_type=payload.type,
        payload=payload.model_dump(),
    )
    return {"received": True}
