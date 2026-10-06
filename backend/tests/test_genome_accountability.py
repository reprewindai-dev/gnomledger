"""Registration records who owns an agent, what it may and may not do, who can stop it, which
CAPPO capability packages it may mount, and digests of its configuration.

Audit (2026-10-06): the genome held model and free-text permission fields only, and the
agent's "creator" was a free string, so a registration answered neither "who is accountable"
nor "what are its limits". All new fields are optional; old-shape clients keep working and
keep their genome hashes.
"""

from __future__ import annotations

import pytest

from app import models
from app.schemas import GenomePayload
from app.utils import stable_hash

from .audit_support import FULL_GENOME, LEGACY_GENOME, genome, make_world, register, registration


@pytest.fixture
def world(session):
    return make_world(session)


def test_old_shape_genome_keeps_its_hash_and_stored_form(world):
    created = register(world, registration(LEGACY_GENOME))

    version = world["session"].query(models.GenomeVersion).one()
    # Exactly what the service hashed and stored before the new fields existed.
    assert version.payload == LEGACY_GENOME
    assert version.genome_hash == stable_hash(LEGACY_GENOME)
    assert created["genome"]["log_retention_days"] == 180
    assert created["genome"]["regulatory_risk_class"] == "unassessed"


def test_full_registration_round_trips_every_field(world):
    created = register(world)
    detail = world["client"].get(f"/api/v1/agents/{created['agent_id']}", headers=world["viewer"])

    assert detail.status_code == 200
    returned = detail.json()["genome"]
    for field, value in FULL_GENOME.items():
        assert returned[field] == value, field
    version = world["session"].query(models.GenomeVersion).one()
    assert version.genome_hash == stable_hash(GenomePayload(**FULL_GENOME).canonical())


def test_retention_below_six_months_is_refused_with_the_reason(world):
    body = registration(genome(log_retention_days=90))
    response = world["client"].post("/api/v1/agents", json=body, headers=world["operator"])

    assert response.status_code == 422
    message = str(response.json()["detail"])
    assert "at least 180" in message
    assert "Article 19" in message
    assert world["session"].query(models.Agent).count() == 0


def test_prompt_text_is_refused_and_only_its_digest_is_stored(world):
    leaked = registration(genome(system_prompt="You are a careful assistant."))
    response = world["client"].post("/api/v1/agents", json=leaked, headers=world["operator"])
    assert response.status_code == 422
    assert "system_prompt_sha256" in str(response.json()["detail"])

    register(world)
    stored = world["session"].query(models.GenomeVersion).one().payload
    assert stored["system_prompt_sha256"] == FULL_GENOME["system_prompt_sha256"]
    assert "careful assistant" not in str(stored)


@pytest.mark.parametrize(
    "overrides",
    [
        {"data_categories": ["personal", "biometric"]},
        {"data_categories": ["none", "personal"]},
        {"regulatory_risk_class": "very_high"},
        {"capability_refs": ["not a ref"]},
        {"incident_contact": "call Dana"},
        {"accountable_owner": {"name": "Dana", "email": "not-an-email"}},
        {"accountable_owner": {"email": "dana@example.com"}},
        {"system_prompt_sha256": "abc"},
        {"code_commit": "not-hex"},
        {"image_digest": "latest"},
        {"out_of_scope_uses": [""]},
    ],
)
def test_malformed_accountability_fields_are_rejected(world, overrides):
    body = registration(genome(**overrides))
    response = world["client"].post("/api/v1/agents", json=body, headers=world["operator"])

    assert response.status_code == 422, overrides


def test_incident_contact_accepts_email_or_url():
    for contact in ("security@example.com", "https://example.com/report"):
        assert GenomePayload(**genome(incident_contact=contact)).incident_contact == contact


def test_free_text_permissions_and_capability_refs_are_both_recorded(world):
    created = register(world, registration(genome(capability_refs=["b.pkg@v2", "a.pkg@v1"])))

    assert created["genome"]["permissions"] == ["read"]
    assert created["genome"]["capability_refs"] == ["a.pkg@v1", "b.pkg@v2"]
