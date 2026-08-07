from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from .schemas import LedgerEventResponse


class PublicLedgerProofResponse(BaseModel):
    """Minimal public evidence that a supplied hash maps to a stored ledger event.

    This surface intentionally excludes actor, summary, arbitrary event details,
    event identifiers, and other tenant-scoped metadata. A database lookup is not
    cryptographic verification of the underlying event or chain.
    """

    event_hash: str
    event_type: str
    created_at: datetime
    prev_event_hash: str | None
    persisted: bool
    status: Literal["RECORDED_HASH_MATCH"] = "RECORDED_HASH_MATCH"
    cryptographic_verification: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"


def to_public_ledger_proof(event: LedgerEventResponse) -> PublicLedgerProofResponse:
    return PublicLedgerProofResponse(
        event_hash=event.event_hash,
        event_type=event.event_type,
        created_at=event.created_at,
        prev_event_hash=event.prev_event_hash,
        persisted=event.persisted,
    )
