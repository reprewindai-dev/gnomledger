"""Signed checkpoints let an outside party detect truncation or rewrite of an agent's chain.

Audit (2026-10-06): the chain was hash-linked but unsigned and unanchored, so deleting the
newest events, or rewriting history and recomputing every later hash, left a chain that
still verified. A checkpoint copy held outside the ledger now exposes both.
"""

from __future__ import annotations

import copy

import pytest
from sqlalchemy import delete, update

from app import models
from app.utils import canonical_timestamp, stable_hash

from .audit_support import make_world, register

VERIFY = "/api/v1/ledger/checkpoints/verify"


@pytest.fixture
def world(session):
    world = make_world(session)
    world["agent_id"] = register(world)["agent_id"]
    for n in range(3):
        _append(world, f"deploy-{n}")
    return world


def _append(world, summary):
    response = world["client"].post(
        "/api/v1/ledger/events",
        json={
            "agent_id": world["agent_id"],
            "event_type": "deployment",
            "actor": "release-bot",
            "summary": summary,
            "details": {"summary": summary},
        },
        headers=world["operator"],
    )
    assert response.status_code == 201, response.text


def _checkpoint(world, key="viewer"):
    return world["client"].get(
        f"/api/v1/ledger/agents/{world['agent_id']}/checkpoint", headers=world[key]
    )


def _verify(world, checkpoint):
    response = world["client"].post(VERIFY, json=checkpoint)  # public: no API key
    assert response.status_code == 200, response.text
    return response.json()


def _chain(session):
    return (
        session.query(models.LedgerEvent)
        .order_by(models.LedgerEvent.created_at, models.LedgerEvent.id)
        .all()
    )


def test_checkpoint_is_signed_and_verifies_while_the_chain_grows(world):
    checkpoint = _checkpoint(world).json()
    chain = _chain(world["session"])

    assert checkpoint["agent_id"] == world["agent_id"]
    assert checkpoint["event_count"] == len(chain) == 4
    assert checkpoint["head_event_hash"] == chain[-1].event_hash
    assert checkpoint["signature"]["algorithm"] == "Ed25519"
    assert _verify(world, checkpoint) == {
        "valid": True,
        "signature_valid": True,
        "key_id_known": True,
        "agent_found": True,
        "chain_intact": True,
        "extends_checkpoint": True,
        "reason": "The ledger extends the checkpoint.",
    }

    _append(world, "deploy-later")
    assert _verify(world, checkpoint)["valid"] is True


def test_truncation_is_detected(world):
    checkpoint = _checkpoint(world).json()
    session = world["session"]
    newest = _chain(session)[-1]

    session.execute(delete(models.LedgerEvent).where(models.LedgerEvent.id == newest.id))
    session.commit()
    session.expire_all()

    result = _verify(world, checkpoint)
    assert result["signature_valid"] is True
    assert result["chain_intact"] is True  # the shortened chain is internally consistent
    assert result["extends_checkpoint"] is False
    assert result["valid"] is False
    assert "truncation" in result["reason"]


def test_truncation_then_regrowth_to_the_same_length_is_detected(world):
    checkpoint = _checkpoint(world).json()
    session = world["session"]
    session.execute(delete(models.LedgerEvent).where(models.LedgerEvent.id == _chain(session)[-1].id))
    session.commit()
    session.expire_all()
    _append(world, "replacement")

    result = _verify(world, checkpoint)
    assert result["extends_checkpoint"] is False
    assert "rewritten" in result["reason"]


def test_rewrite_with_recomputed_hashes_is_detected(world):
    checkpoint = _checkpoint(world).json()
    session = world["session"]
    agent_id = world["agent_id"]

    # Rewrite the second event and re-link every later event, so the chain verifies alone.
    previous = None
    for index, event in enumerate(_chain(session)):
        details = {"summary": "rewritten"} if index == 1 else event.details
        new_hash = stable_hash(
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "agent_id": agent_id,
                "actor": event.actor,
                "summary": event.summary,
                "details": details,
                "prev_event_hash": previous,
                "created_at": canonical_timestamp(event.created_at),
            }
        )
        session.execute(
            update(models.LedgerEvent)
            .where(models.LedgerEvent.id == event.id)
            .values(details=details, prev_event_hash=previous, event_hash=new_hash)
        )
        previous = new_hash
    session.commit()
    session.expire_all()

    chain_check = world["client"].get(
        f"/api/v1/ledger/agents/{agent_id}/verify", headers=world["viewer"]
    )
    assert chain_check.json()["status"] == "verified"  # the hash chain alone cannot tell

    result = _verify(world, checkpoint)
    assert result["chain_intact"] is True
    assert result["extends_checkpoint"] is False
    assert result["valid"] is False
    assert "rewritten" in result["reason"]


def test_naive_tamper_breaks_the_chain(world):
    checkpoint = _checkpoint(world).json()
    session = world["session"]
    first = _chain(session)[0]
    session.execute(
        update(models.LedgerEvent)
        .where(models.LedgerEvent.id == first.id)
        .values(details={"tampered": True})
    )
    session.commit()
    session.expire_all()

    result = _verify(world, checkpoint)
    assert result["chain_intact"] is False
    assert result["valid"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [("event_count", 1), ("head_event_hash", "0" * 64), ("agent_id", "agent_other"), ("issued_at", "2030-01-01T00:00:00+00:00")],
)
def test_altered_checkpoint_fails_signature_and_discloses_nothing(world, field, value):
    checkpoint = copy.deepcopy(_checkpoint(world).json())
    checkpoint[field] = value

    result = _verify(world, checkpoint)
    assert result["signature_valid"] is False
    assert result["valid"] is False
    assert result["agent_found"] is None
    assert result["extends_checkpoint"] is None


def test_unknown_key_id_is_reported(world):
    checkpoint = _checkpoint(world).json()
    checkpoint["key_id"] = checkpoint["signature"]["key_id"] = "pgl-ed25519-0000000000000000"

    result = _verify(world, checkpoint)
    assert result["key_id_known"] is False
    assert result["signature_valid"] is False


def test_checkpoint_issue_is_account_scoped(world):
    assert _checkpoint(world, key="outsider").status_code == 404
    assert world["client"].get(
        f"/api/v1/ledger/agents/{world['agent_id']}/checkpoint"
    ).status_code == 401
