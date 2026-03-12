from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models


class BillingService:
    def __init__(self, db: Session):
        self.db = db

    def record_usage(
        self,
        account_id: int,
        metric: str,
        amount: float,
        period_start: datetime,
        period_end: datetime,
    ) -> models.BillingUsage:
        usage = models.BillingUsage(
            account_id=account_id,
            metric=metric,
            amount=Decimal(str(amount)),
            period_start=period_start,
            period_end=period_end,
        )
        self.db.add(usage)
        self.db.commit()
        self.db.refresh(usage)
        return usage

    def ensure_quota(self, account_id: int, metric: str, limit: float) -> bool:
        stmt = select(models.BillingUsage).where(
            models.BillingUsage.account_id == account_id,
            models.BillingUsage.metric == metric,
        )
        total = sum(float(row.amount) for row in self.db.scalars(stmt))
        return total < limit

    def list_usage(self, account_id: int) -> list[models.BillingUsage]:
        stmt = (
            select(models.BillingUsage)
            .where(models.BillingUsage.account_id == account_id)
            .order_by(models.BillingUsage.period_start.desc())
        )
        return list(self.db.scalars(stmt))

    def record_stripe_event(self, event_id: str, event_type: str, payload: dict) -> models.BillingEvent:
        event = models.BillingEvent(
            stripe_event_id=event_id,
            event_type=event_type,
            payload=payload,
        )
        self.db.add(event)
        self.db.commit()
        return event
