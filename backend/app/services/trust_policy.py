from typing import Any

from ..models import LedgerEvent
from ..utils import canonical_timestamp


class TrustPolicyV1:
    """Canonical V1 trust policy logic for Gnomledger agents."""

    @staticmethod
    def calculate_trust(events: list[LedgerEvent]) -> dict[str, Any]:
        """Calculate trust score based on V1 rules."""
        base_score = 50.0
        evidence_head = None

        if events:
            # Normalize timestamps because SQLite returns naive values for
            # timezone-aware columns; unsaved events may not have an id yet.
            latest_event = max(
                events,
                key=lambda event: (canonical_timestamp(event.created_at), event.id or 0),
            )
            evidence_head = latest_event.event_hash

        for event in events:
            if event.event_type == "birth_registration":
                base_score = max(base_score, 50.0)
            elif event.event_type == "deployment":
                base_score += 10.0
            elif event.event_type == "test_audit":
                base_score += event.details.get("score", 0) / 10.0
            elif event.event_type == "violation":
                base_score -= 20.0

        trust_score = max(0.0, min(100.0, base_score))

        if trust_score >= 90:
            risk_tier = "production"
        elif trust_score >= 70:
            risk_tier = "standard"
        elif trust_score >= 40:
            risk_tier = "sandbox"
        else:
            risk_tier = "terminated"

        return {
            "trust_score": float(trust_score),
            "risk_tier": risk_tier,
            "trust_policy_version": "v1",
            "evidence_head": evidence_head,
        }
