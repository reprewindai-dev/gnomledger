"""The audit bundle: the one document an auditor downloads, verifiable offline.

Audit (2026-10-06): evidence about an agent was spread over five endpoints, none signed, and
the export carried only the newest 500 events with no way to prove it was complete.
"""

from __future__ import annotations

import base64
import copy

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import update

from app import models
from app.services.signing_service import canonical_json_bytes
from app.utils import stable_hash

from .audit_support import LEGACY_GENOME, make_world, register


@pytest.fixture
def world(session):
    world = make_world(session)
    agent = register(world)
    world["agent_id"] = agent["agent_id"]
    world["path"] = f"/api/v1/ledger/agents/{agent['agent_id']}/audit-bundle"
    client = world["client"]
    client.patch(
        f"/api/v1/agents/{agent['agent_id']}/genome",
        json={"reason": "model upgrade", "changes": {**LEGACY_GENOME, "model_version": "2"}},
        headers=world["operator"],
    )
    client.post(
        "/api/v1/ledger/events",
        json={
            "agent_id": agent["agent_id"],
            "event_type": "deployment",
            "actor": "release-bot",
            "summary": "deployed",
            "details": {"env": "prod"},
        },
        headers=world["operator"],
    )
    return world


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _verifies(jwk: dict, document: dict, signature: dict) -> bool:
    key = Ed25519PublicKey.from_public_bytes(_b64url_decode(jwk["x"]))
    try:
        key.verify(_b64url_decode(signature["value"]), canonical_json_bytes(document))
    except InvalidSignature:
        return False
    return True


def _bundle(world, key="viewer"):
    response = world["client"].get(world["path"], headers=world[key])
    assert response.status_code == 200, response.text
    return response.json()


def test_bundle_contains_the_whole_record_and_verifies_offline(world):
    bundle = _bundle(world)
    jwk = bundle["signing_key"]["jwk"]

    assert bundle["schema_version"] == "pgl.audit_bundle.v1"
    assert bundle["key_id"] == jwk["kid"] == bundle["bundle_signature"]["key_id"]
    assert bundle["agent"]["agent_id"] == world["agent_id"]
    assert [v["version"] for v in bundle["genome_versions"]] == [1, 2]
    assert [e["event_type"] for e in bundle["events"]] == [
        "birth_registration",
        "mutation_update",
        "deployment",
    ]
    assert bundle["checkpoint"]["event_count"] == 3
    assert bundle["checkpoint"]["head_event_hash"] == bundle["events"][-1]["event_hash"]
    assert bundle["verification"]["chain"]["status"] == "verified"
    assert bundle["verification"]["certificate_signature_valid"] is True
    assert bundle["verification"]["genome_hashes_valid"] is True
    assert bundle["limitations"]

    # Everything below uses only the bundle's own contents.
    signed = {k: v for k, v in bundle.items() if k != "bundle_signature"}
    assert _verifies(jwk, signed, bundle["bundle_signature"])
    certificate = bundle["certificate"]
    assert _verifies(jwk, certificate["certificate"], certificate["signature"])
    checkpoint = {k: v for k, v in bundle["checkpoint"].items() if k != "signature"}
    assert _verifies(jwk, checkpoint, bundle["checkpoint"]["signature"])
    for version in bundle["genome_versions"]:
        assert stable_hash(version["payload"]) == version["genome_hash"]
    previous = None
    for event in bundle["events"]:
        assert event["prev_event_hash"] == previous
        previous = event["event_hash"]


def test_altered_bundle_fails_its_signature(world):
    bundle = _bundle(world)
    jwk = bundle["signing_key"]["jwk"]
    altered = copy.deepcopy({k: v for k, v in bundle.items() if k != "bundle_signature"})
    altered["events"].pop()

    assert not _verifies(jwk, altered, bundle["bundle_signature"])


def test_bundle_checkpoint_is_accepted_by_public_verify(world):
    checkpoint = _bundle(world)["checkpoint"]

    result = world["client"].post("/api/v1/ledger/checkpoints/verify", json=checkpoint).json()
    assert result["valid"] is True


def test_bundle_is_account_scoped(world):
    assert world["client"].get(world["path"], headers=world["outsider"]).status_code == 404
    assert world["client"].get(world["path"]).status_code == 401


def test_bundle_reports_a_tampered_chain(world):
    session = world["session"]
    event = session.query(models.LedgerEvent).filter_by(event_type="deployment").one()
    session.execute(
        update(models.LedgerEvent)
        .where(models.LedgerEvent.id == event.id)
        .values(details={"env": "tampered"})
    )
    session.commit()
    session.expire_all()

    bundle = _bundle(world)
    assert bundle["verification"]["chain"]["status"] == "blocked"
    assert bundle["verification"]["chain"]["valid"] is False


def test_bundle_after_decommission_keeps_every_event(world):
    client = world["client"]
    response = client.post(
        f"/api/v1/agents/{world['agent_id']}/decommission",
        json={"reason": "retired"},
        headers=world["operator"],
    )
    assert response.status_code == 200

    bundle = _bundle(world)
    assert bundle["agent"]["status"] == "decommissioned"
    assert [e["event_type"] for e in bundle["events"]][-1] == "decommission"
    assert len(bundle["events"]) == 4
    assert bundle["verification"]["chain"]["status"] == "verified"


def test_event_hashes_in_the_bundle_recompute_from_the_bundle_alone(world):
    bundle = _bundle(world)
    for exported in bundle["events"]:
        assert exported["event_hash"] == stable_hash(
            {
                "event_id": exported["event_id"],
                "event_type": exported["event_type"],
                "agent_id": world["agent_id"],
                "actor": exported["actor"],
                "summary": exported["summary"],
                "details": exported["details"],
                "prev_event_hash": exported["prev_event_hash"],
                "created_at": exported["created_at_canonical"],
            }
        )
