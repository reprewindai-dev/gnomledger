"""Genome updates record who changed what and why, and the change record commits with the
new version.

Audit (2026-10-06): PATCH /genome took a free-text actor, recorded the new hash only, logged
the agent's intended_use as the event actor, and committed the version before (and apart
from) its ledger event.
"""

from __future__ import annotations

import pytest

from app import models

from .audit_support import FULL_GENOME, LEGACY_GENOME, make_world, register, registration


@pytest.fixture
def world(session):
    world = make_world(session)
    world["agent"] = register(world)
    world["path"] = f"/api/v1/agents/{world['agent']['agent_id']}/genome"
    return world


def _events(world, event_type="mutation_update"):
    return (
        world["session"]
        .query(models.LedgerEvent)
        .filter_by(event_type=event_type)
        .order_by(models.LedgerEvent.id)
        .all()
    )


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_genome_update_without_a_reason_is_rejected(world, reason):
    body = {"changes": {**LEGACY_GENOME, "model_version": "2"}}
    if reason is not None:
        body["reason"] = reason

    response = world["client"].patch(world["path"], json=body, headers=world["operator"])

    assert response.status_code == 422
    assert world["session"].query(models.GenomeVersion).count() == 1
    assert _events(world) == []


def test_genome_update_records_changer_reason_and_both_hashes(world):
    body = {
        "actor": "dana.reyes@example.com",
        "note": "Model upgrade",
        "reason": "CAB-1142 approved by CRO",
        "changes": {**LEGACY_GENOME, "model_version": "2"},
    }
    response = world["client"].patch(world["path"], json=body, headers=world["operator"])
    assert response.status_code == 200

    v1, v2 = world["session"].query(models.GenomeVersion).order_by(models.GenomeVersion.version)
    (event,) = _events(world)
    details = event.details
    operator_key = world["session"].query(models.ApiKey).filter_by(role="operator").one()

    assert details["reason"] == "CAB-1142 approved by CRO"
    assert details["declared_actor"] == "dana.reyes@example.com"
    assert details["changed_by"]["api_key_id"] == operator_key.id
    assert details["changed_by"]["account_id"] == world["account"].id
    assert details["changed_by"]["role"] == "operator"
    assert event.actor.startswith(f"api_key:{operator_key.id}:")
    assert details["previous_genome_hash"] == v1.genome_hash
    assert details["new_genome_hash"] == v2.genome_hash
    assert (details["previous_version"], details["new_version"]) == (1, 2)
    assert details["changed_fields"] == ["model_version"]


def test_old_shape_update_keeps_accountability_fields_and_new_fields_can_change(world):
    old_client = {"reason": "patch", "changes": {**LEGACY_GENOME, "model_version": "2"}}
    kept = world["client"].patch(world["path"], json=old_client, headers=world["operator"])
    assert kept.status_code == 200
    assert kept.json()["accountable_owner"] == FULL_GENOME["accountable_owner"]
    assert kept.json()["capability_refs"] == FULL_GENOME["capability_refs"]

    new_owner = {"name": "Sam Ortiz", "email": "sam.ortiz@example.com"}
    handover = {
        "reason": "ownership handover",
        "changes": {**LEGACY_GENOME, "model_version": "2", "accountable_owner": new_owner},
    }
    changed = world["client"].patch(world["path"], json=handover, headers=world["operator"])
    assert changed.status_code == 200
    assert changed.json()["accountable_owner"]["name"] == "Sam Ortiz"
    assert _events(world)[-1].details["changed_fields"] == ["accountable_owner"]


def test_unchanged_genome_is_a_conflict_and_appends_nothing(world):
    body = {"reason": "no-op", "changes": FULL_GENOME}
    response = world["client"].patch(world["path"], json=body, headers=world["operator"])

    assert response.status_code == 409
    assert world["session"].query(models.GenomeVersion).count() == 1
    assert _events(world) == []


def test_viewer_cannot_change_a_genome(world):
    body = {"reason": "r", "changes": {**LEGACY_GENOME, "model_version": "2"}}
    assert world["client"].patch(world["path"], json=body, headers=world["viewer"]).status_code == 403


def test_old_shape_registration_can_still_be_updated(world):
    legacy = register(world, registration(LEGACY_GENOME))
    path = f"/api/v1/agents/{legacy['agent_id']}/genome"
    body = {"reason": "upgrade", "changes": {**LEGACY_GENOME, "model_version": "2"}}

    response = world["client"].patch(path, json=body, headers=world["operator"])

    assert response.status_code == 200
    assert response.json()["model_version"] == "2"
