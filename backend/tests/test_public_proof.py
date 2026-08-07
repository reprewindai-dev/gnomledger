from datetime import datetime, timezone

from backend.app.public_proof import to_public_ledger_proof
from backend.app.schemas import LedgerEventResponse


def test_public_ledger_proof_excludes_tenant_payload() -> None:
    event = LedgerEventResponse(
        event_id="evt_secret",
        event_type="pre_execution_authorization",
        actor="operator@example.test",
        summary="sensitive summary",
        details={
            "workspace_id": "workspace-secret",
            "run_id": "run-secret",
            "provenance": {"internal": "secret"},
        },
        prev_event_hash="prev-hash",
        event_hash="event-hash",
        created_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
        persisted=True,
        chain_head="event-hash",
    )

    payload = to_public_ledger_proof(event).model_dump(mode="json")

    assert payload["event_hash"] == "event-hash"
    assert payload["status"] == "RECORDED_HASH_MATCH"
    assert payload["cryptographic_verification"] == "NOT_VERIFIED"
    assert payload["persisted"] is True

    for sensitive_field in ("event_id", "actor", "summary", "details", "chain_head"):
        assert sensitive_field not in payload
