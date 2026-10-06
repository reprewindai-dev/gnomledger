"""Repository text must not overclaim what the ledger provides.

The ledger is hash-chained, so tampering is detectable (tamper-evident), but events are
unsigned and not anchored anywhere external, so it is not immutable or tamper-proof; and
there is no JWT issuance or per-minute rate limiting in the service.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

OVERCLAIMS = ("immutable operational history", "tamper-proof", "Signed JWT", "requests per minute")


@pytest.mark.parametrize("relative", ["index.html", "docs/revenue-model.md", "README.md"])
def test_repo_text_does_not_overclaim_ledger_guarantees(relative: str) -> None:
    text = (REPO / relative).read_text(encoding="utf-8")

    found = [claim for claim in OVERCLAIMS if claim in text]
    assert not found, f"{relative} still claims: {found}"


def test_readme_does_not_call_the_service_production_ready() -> None:
    assert "production-ready" not in (REPO / "README.md").read_text(encoding="utf-8")
