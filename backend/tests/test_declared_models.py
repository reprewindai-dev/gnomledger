"""A genome declares every model a kind of agent may use; each ephemeral task records the
model it actually used, which must be a declared one.

Design (2026-10-06): Veklom agents are ephemeral task agents. The genome is the register-
once identity of a kind of agent and real agents orchestrate several models, so a single
model_family / model_version could not describe them. The single-model fields stay accepted
and read as one declared model.
"""

from __future__ import annotations

import pytest

from app import models
from app.utils import stable_hash

from .audit_support import LEGACY_GENOME, genome, make_world, register, registration

MODELS = [
    {"provider": "Anthropic", "identifier": "claude-opus-5-5", "role": "planner"},
    {"provider": "self-hosted", "identifier": "sha256:" + "b" * 64, "role": "embedding"},
]


def _multi_model_genome(**overrides):
    body = genome(declared_models=MODELS, **overrides)
    for field in ("model_family", "model_version", "architecture", "model_provider", "model_identifier"):
        body.pop(field)
    return body


@pytest.fixture
def world(session):
    return make_world(session)


def test_multi_model_genome_registers_without_single_model_fields(world):
    created = register(world, registration(_multi_model_genome()))

    stored = world["session"].query(models.GenomeVersion).one()
    assert "model_family" not in stored.payload
    assert stored.payload["declared_models"] == [
        {**m, "family": None, "version": None} for m in MODELS
    ]
    assert created["genome"]["model_family"] is None
    model_block = created["certificate"]["certificate"]["model"]
    assert model_block["declared_models_source"] == "declared_models"
    assert [m["identifier"] for m in model_block["declared_models"]] == [
        "claude-opus-5-5",
        "sha256:" + "b" * 64,
    ]
    assert "statement" in model_block and "model_used" in model_block["statement"]
    gaps = created["certificate"]["missing_accountability_fields"]
    assert not [g for g in gaps if g.startswith("declared_models")]


def test_old_single_model_shape_reads_as_one_declared_model(world):
    created = register(world, registration(LEGACY_GENOME))

    model_block = created["certificate"]["certificate"]["model"]
    assert model_block["declared_models_source"] == "single_model_fields"
    assert model_block["declared_models"] == [
        {
            "provider": None,
            "identifier": None,
            "role": "primary",
            "family": "transformer",
            "version": "1",
        }
    ]
    stored = world["session"].query(models.GenomeVersion).one()
    assert stored.genome_hash == stable_hash(LEGACY_GENOME)  # hash unchanged


@pytest.mark.parametrize(
    "body",
    [
        {k: v for k, v in LEGACY_GENOME.items() if k not in ("model_family", "model_version")},
        {k: v for k, v in LEGACY_GENOME.items() if k != "model_version"},
        genome(declared_models=MODELS, model_identifier="gpt-unknown"),
        genome(declared_models=[{"provider": "Anthropic"}]),
    ],
)
def test_model_declaration_must_be_present_and_consistent(world, body):
    response = world["client"].post(
        "/api/v1/agents", json=registration(body), headers=world["operator"]
    )
    assert response.status_code == 422


def _validate(world, agent_id, model_used=None):
    genome_hash = world["session"].query(models.GenomeVersion).filter(
        models.GenomeVersion.agent_id == world["session"].query(models.Agent).filter_by(
            agent_id=agent_id
        ).one().id
    ).one().genome_hash
    body = {
        "agent_id": agent_id,
        "workspace_id": "ws-1",
        "requested_tools": [],
        "expected_genome_hash": genome_hash,
    }
    if model_used is not None:
        body["model_used"] = model_used
    response = world["client"].post(
        "/api/v1/agents/execution/validate", json=body, headers=world["operator"]
    )
    assert response.status_code == 200
    return response.json()


def test_execution_validate_refuses_an_undeclared_model(world):
    agent_id = register(world, registration(_multi_model_genome()))["agent_id"]

    assert _validate(world, agent_id)["model_used_declared"] is None
    declared = _validate(world, agent_id, "claude-opus-5-5")
    assert (declared["allowed"], declared["model_used_declared"]) == (True, True)
    qualified = _validate(world, agent_id, "Anthropic/claude-opus-5-5")
    assert qualified["model_used_declared"] is True
    undeclared = _validate(world, agent_id, "gpt-unknown")
    assert (undeclared["allowed"], undeclared["model_used_declared"]) == (False, False)


def test_single_model_genome_matches_its_identifier_or_family(world):
    full = register(world)["agent_id"]
    assert _validate(world, full, "claude-opus-5-5")["model_used_declared"] is True
    assert _validate(world, full, "other-model")["allowed"] is False

    legacy = register(world, registration(LEGACY_GENOME))["agent_id"]
    assert _validate(world, legacy, "transformer:1")["model_used_declared"] is True


def test_updates_keep_the_model_declaration_the_client_did_not_send(world):
    multi = register(world, registration(_multi_model_genome()))["agent_id"]
    old_client = {"reason": "tools", "changes": {**LEGACY_GENOME, "tools": ["browser", "ocr"]}}
    response = world["client"].patch(
        f"/api/v1/agents/{multi}/genome", json=old_client, headers=world["operator"]
    )
    assert response.status_code == 200
    assert [m["identifier"] for m in response.json()["declared_models"]] == [
        "claude-opus-5-5",
        "sha256:" + "b" * 64,
    ]

    legacy = register(world, registration(LEGACY_GENOME))["agent_id"]
    new_client = {
        "reason": "now multi-model",
        "changes": {
            k: v for k, v in LEGACY_GENOME.items() if k not in ("model_family", "model_version", "architecture")
        }
        | {"declared_models": MODELS},
    }
    response = world["client"].patch(
        f"/api/v1/agents/{legacy}/genome", json=new_client, headers=world["operator"]
    )
    assert response.status_code == 200
    assert response.json()["model_family"] == "transformer"
    assert len(response.json()["declared_models"]) == 2


def test_execution_evidence_carries_model_used(world):
    agent_id = register(world)["agent_id"]
    details = {
        "schema_version": "pgl.post_execution_attestation.v1",
        "run_id": "run-1",
        "agent_id": agent_id,
        "pre_authorization_event_id": "evt_x",
        "output_hash": "o",
        "outcome_hash": "c",
        "governance_decision": "allow",
        "actor_id": None,
        "provenance": {},
        "model_used": "claude-opus-5-5",
    }
    response = world["client"].post(
        "/api/v1/ledger/events",
        json={
            "agent_id": agent_id,
            "event_type": "post_execution_attestation",
            "actor": "cappo",
            "summary": "task done",
            "details": details,
        },
        headers=world["operator"],
    )
    assert response.status_code == 201
    assert response.json()["details"]["model_used"] == "claude-opus-5-5"
