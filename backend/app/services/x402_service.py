"""
x402 pricing for PGL — pay-per-call access with no subscription required.

This is the machine-caller path: an agent that just needs to mint one
certificate or write one ledger event pays a fraction of a cent via the x402
protocol (HTTP 402 Payment Required, https://x402.org) instead of signing up
for a subscription tier. Subscription tiers (see billing_service.py) remain
the path for humans/teams who want predictable monthly cost and higher
volume; both paths hit the same underlying endpoints.

Prices are in USDC, expressed as strings to avoid float precision issues in
the x402 payment payload (matches the x402 spec's maxAmountRequired format,
which is a decimal string of the smallest asset unit — see _to_atomic_units).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..config import get_settings

USDC_DECIMALS = 6  # USDC on Base uses 6 decimal places


@dataclass(frozen=True)
class X402Price:
    resource: str
    method: str
    price_usdc: Decimal
    description: str


# Decided pricing — reads are always free (verification is the trust feature,
# never gate it). Writes are priced per real cost + margin.
PRICING: list[X402Price] = [
    X402Price("/api/v1/agents", "POST", Decimal("0.01"), "Mint an agent birth certificate"),
    X402Price("/api/v1/ledger/events", "POST", Decimal("0.001"), "Write a ledger event"),
    X402Price("/api/v1/agents/{agent_id}/genome", "PATCH", Decimal("0.005"), "Update agent genome"),
    X402Price("/api/v1/notary/chat", "POST", Decimal("0.002"), "Notary AI compliance chat (covers model cost)"),
]

_PRICE_INDEX = {(p.resource, p.method): p for p in PRICING}


def get_price(resource: str, method: str) -> X402Price | None:
    return _PRICE_INDEX.get((resource, method))


def _to_atomic_units(amount: Decimal) -> str:
    """Convert a decimal USDC amount to the atomic unit string x402 expects."""
    return str(int(amount * (10 ** USDC_DECIMALS)))


def build_discovery_manifest() -> dict:
    """
    Returns the machine-readable manifest served at GET /.well-known/x402.
    Any agent can fetch this with zero auth to learn what's payable and how.
    """
    settings = get_settings()

    if not settings.x402_pay_to_address:
        # Honest state: discovery still works so tooling can introspect
        # pricing, but nothing is actually payable until a real wallet is
        # configured. This is a real deployment blocker, not a bug.
        pay_to = "NOT_CONFIGURED — set X402_PAY_TO_ADDRESS before going live"
    else:
        pay_to = settings.x402_pay_to_address

    return {
        "x402Version": 1,
        "resources": [
            {
                "resource": p.resource,
                "method": p.method,
                "description": p.description,
                "accepts": [
                    {
                        "scheme": "exact",
                        "network": settings.x402_network,
                        "maxAmountRequired": _to_atomic_units(p.price_usdc),
                        "resource": p.resource,
                        "description": p.description,
                        "mimeType": "application/json",
                        "payTo": pay_to,
                        "asset": settings.x402_asset,
                        "extra": {"price_display": f"${p.price_usdc} {settings.x402_asset}"},
                    }
                ],
            }
            for p in PRICING
        ],
    }
