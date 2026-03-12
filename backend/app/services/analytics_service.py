from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models


class AnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def track(self, event_type: str, payload: dict, account_id: int | None = None) -> models.AnalyticsEvent:
        event = models.AnalyticsEvent(
            event_type=event_type,
            payload=payload,
            account_id=account_id,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event
