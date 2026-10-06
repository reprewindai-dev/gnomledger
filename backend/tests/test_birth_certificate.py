"""Birth certificates are signed with the ledger's Ed25519 key and say which accountability
fields were not supplied.

Audit (2026-10-06): the certificate was unsigned JSON carrying only a genome hash, and an
old-shape registration produced a certificate that was silent about everything it lacked.
"""

from __future__ import annotations

import base64
import copy
import json

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import delete

from app import models
from app.services.lineage_service import LineageService
from app.services.signing_service import canonical_json_bytes

from .audit_support import LEGACY_GENOME, genome, make_world, register, registration

TOP_LEVEL_GAPS = [
    "accountable_owner",
    "incident_contact",
    "deployer",
    "provider",
    "declared_models[].provider",
    "declared_models[].identifier",
    "out_of_scope_uses",
    "known_limitations",
    "data_categories",
    "regulatory_risk_class",
    "risk_rationale",
    "oversight",
    "run_mode",
    "capability_refs",
]


@pytest.fixture
def world(session):
    return make_world(session)


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _verifies_with_published_key(client, document: dict, signature: dict) -> bool:
    jwk = client.get("/.well-known/pgl-signing-key").json()["jwk"]
    if signature["key_id"] != jwk["kid"]:
        return False
    public_key = Ed25519PublicKey.from_public_bytes(_b64url_decode(jwk["x"]))
    try:
        public_key.verify(_b64url_decode(signature["value"]), canonical_json_bytes(document))
    except InvalidSignature:
        return False
    return True


def test_old_shape_registration_still_works_and_lists_every_gap(world):
    created = register(world, registration(LEGACY_GENOME))
    certificate = created["certificate"]

    assert certificate["signature_status"] == "signed"
    assert certificate["missing_accountability_fields"] == TOP_LEVEL_GAPS
    assert certificate["missing_integrity_fields"] == [
        "system_prompt_sha256",
        "code_commit",
        "image_digest",
        "tool_versions",
    ]
    assert certificate["certificate"]["missing_accountability_fields"] == TOP_LEVEL_GAPS

    fetched = world["client"].get(
        f"/api/v1/agents/{created['agent_id']}/certificate", headers=world["viewer"]
    )
    assert fetched.status_code == 200
    assert fetched.json()["missing_accountability_fields"] == TOP_LEVEL_GAPS
    assert fetched.json()["signature"] == certificate["signature"]


def test_complete_registration_has_no_gaps_and_partial_blocks_name_members(world):
    complete = register(world)["certificate"]
    assert complete["missing_accountability_fields"] == []
    assert complete["missing_integrity_fields"] == []

    partial = genome(
        accountable_owner={"name": "Dana Reyes"},
        oversight={"stop_mechanism": "CAPPO terminate"},
        regulatory_risk_class="unassessed",
        tool_versions={},
    )
    gaps = register(world, registration(partial))["certificate"]
    assert gaps["missing_accountability_fields"] == [
        "accountable_owner.role",
        "accountable_owner.email",
        "accountable_owner.organization",
        "regulatory_risk_class",
        "oversight.oversight_contact",
        "oversight.escalation_path",
    ]
    assert gaps["missing_integrity_fields"] == ["tool_versions"]


def test_certificate_signature_verifies_with_published_key_and_fails_after_any_change(world):
    certificate = register(world)["certificate"]
    document, signature = certificate["certificate"], certificate["signature"]

    assert signature["algorithm"] == "Ed25519"
    assert signature["key_id"] == certificate["key_id"] == document["key_id"]
    assert _verifies_with_published_key(world["client"], document, signature)

    for field in document:
        altered = copy.deepcopy(document)
        value = altered[field]
        if isinstance(value, dict):
            altered[field] = {**value, "tampered": True}
        elif isinstance(value, list):
            altered[field] = [*value, "tampered"]
        elif isinstance(value, int):
            altered[field] = value + 1
        else:
            altered[field] = f"{value}-tampered"
        assert not _verifies_with_published_key(world["client"], altered, signature), field

    owner_swapped = copy.deepcopy(document)
    owner_swapped["accountability"]["accountable_owner"]["email"] = "someone@else.example"
    assert not _verifies_with_published_key(world["client"], owner_swapped, signature)


def test_certificate_states_that_only_capability_refs_are_enforced(world):
    document = register(world)["certificate"]["certificate"]

    authority = document["authority"]
    assert authority["capability_refs"] == ["veklom.governed-counter@v1"]
    assert authority["capability_enforcement"] == "CAPPO"
    assert authority["declared_permissions"] == ["read"]
    assert authority["permissions_enforcement"] == "declarative"
    assert "not enforced" in authority["statement"]
    assert document["retention"]["log_retention_days"] == 365
    assert document["configuration_integrity"]["image_digest"].endswith("a" * 64)


def test_certificate_artifact_on_disk_carries_the_signature(world):
    created = register(world)
    with open(created["certificate"]["document_uri"], encoding="utf-8") as fp:
        envelope = json.load(fp)

    assert envelope["signature"] == created["certificate"]["signature"]
    assert _verifies_with_published_key(
        world["client"], envelope["certificate"], envelope["signature"]
    )


def test_certificate_issued_before_signing_is_reported_unsigned_with_gaps(world):
    created = register(world, registration(LEGACY_GENOME))
    session = world["session"]
    session.execute(delete(models.CertificateSignature))
    cert = session.query(models.BirthCertificate).one()
    cert.certificate_payload = {"version": 1, "agent_id": created["agent_id"]}
    session.commit()
    session.expire_all()

    fetched = world["client"].get(
        f"/api/v1/agents/{created['agent_id']}/certificate", headers=world["viewer"]
    ).json()

    assert fetched["signature_status"] == "unsigned_legacy"
    assert fetched["signature"] is None
    assert fetched["missing_accountability_fields"] == TOP_LEVEL_GAPS


def test_forked_agent_gets_a_signed_certificate_and_a_birth_event(world):
    parent = register(world)
    child = LineageService(world["session"]).fork_agent(
        account_id=world["account"].id,
        source_agent_id=parent["agent_id"],
        new_name="claims-triage-v2",
        creator="dana.reyes@example.com",
        jurisdiction="EU",
    )

    certificate = child.certificate.model_dump()
    assert certificate["signature_status"] == "signed"
    assert certificate["certificate"]["parent_agent_ids"] == [parent["agent_id"]]
    assert _verifies_with_published_key(
        world["client"], certificate["certificate"], certificate["signature"]
    )
    history = world["client"].get(f"/api/v1/ledger/agents/{child.agent_id}", headers=world["viewer"])
    assert [e["event_type"] for e in history.json()] == ["birth_registration"]
