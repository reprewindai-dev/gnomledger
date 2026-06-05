from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .. import models
from ..utils import utc_now


PLAN_QUOTAS = {
    "launch": {"certificate_issuance": 25, "lineage_render": 3},
    "scale": {"certificate_issuance": 250, "lineage_render": 25},
    "enterprise": {"certificate_issuance": 10000, "lineage_render": 10000},
}


def _month_bucket(dt: datetime) -> tuple[datetime, datetime]:
    period_start = datetime(dt.year, dt.month, 1, tzinfo=dt.tzinfo)
    if dt.month == 12:
        period_end = datetime(dt.year + 1, 1, 1, tzinfo=dt.tzinfo)
    else:
        period_end = datetime(dt.year, dt.month + 1, 1, tzinfo=dt.tzinfo)
    return period_start, period_end


class BillingService:
    def __init__(self, db: Session):
        self.db = db

    def record_usage(
        self,
        account_id: int,
        metric: str,
        amount: float,
    ) -> models.BillingUsage:
        now = utc_now()
        period_start, period_end = _month_bucket(now)
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
        period_start, period_end = _month_bucket(utc_now())
        total = self.db.execute(
            select(func.coalesce(func.sum(models.BillingUsage.amount), 0)).where(
                models.BillingUsage.account_id == account_id,
                models.BillingUsage.metric == metric,
                models.BillingUsage.period_start >= period_start,
                models.BillingUsage.period_end <= period_end,
            )
        ).scalar_one_or_none() or 0
        total = float(total)
        return total < limit

    def list_usage(self, account_id: int) -> list[models.BillingUsage]:
        stmt = (
            select(models.BillingUsage)
            .where(models.BillingUsage.account_id == account_id)
            .order_by(models.BillingUsage.period_start.desc())
        )
        return list(self.db.scalars(stmt))

    def ensure_or_raise(self, account_id: int, metric: str, limit: float) -> None:
        if not self.ensure_quota(account_id=account_id, metric=metric, limit=limit):
            raise ValueError(f"Usage quota exceeded for metric '{metric}'")

    def plan_limit(self, account: models.Account, metric: str) -> float:
        limits = PLAN_QUOTAS.get(account.tier, PLAN_QUOTAS["launch"])
        return float(limits.get(metric, float("inf")))

    def get_current_metric(self, account_id: int, metric: str) -> float:
        period_start, period_end = _month_bucket(utc_now())
        total = self.db.execute(
            select(func.coalesce(func.sum(models.BillingUsage.amount), 0)).where(
                models.BillingUsage.account_id == account_id,
                models.BillingUsage.metric == metric,
                models.BillingUsage.period_start >= period_start,
                models.BillingUsage.period_end <= period_end,
            )
        ).scalar_one_or_none() or 0
        return float(total)

    def record_stripe_event(self, event_id: str, event_type: str, payload: dict) -> models.BillingEvent:
        # Best effort dedupe protection for webhook retries
        existing = self.db.execute(
            select(models.BillingEvent).where(models.BillingEvent.stripe_event_id == event_id)
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        event = models.BillingEvent(
            stripe_event_id=event_id,
            event_type=event_type,
            payload=payload,
        )
        self.db.add(event)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return self.db.execute(
                select(models.BillingEvent).where(models.BillingEvent.stripe_event_id == event_id)
            ).scalar_one()
        self.db.refresh(event)
        return event
