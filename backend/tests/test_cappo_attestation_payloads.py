"""The ledger must accept the exact pre/post execution payloads CAPPO emits.

CAPPO's GnomledgerPGLAdapter builds the full PreExecutionAuthorizationDetails /
PostExecutionAttestationDetails shapes (cappo_backend/services/pgl_adapter.py). This
test reproduces those shapes and asserts the ledger accepts them (201) and threads the
pre event_id into the post attestation — the contract that previously 422'd when CAPPO
sent sparse details.
"""

from __future__ import annotations

import pytest

from .audit_support import make_world, register


@pytest.fixture
def world(session):
    return make_world(session)


def _cappo_pre_details(agent_id: str) -> dict:
    # Mirror of GnomledgerPGLAdapter.mint_pre_certificate details.
    return {
        "schema_version": "pgl.pre_execution_authorization.v1",
        "run_id": "run-1",
        "workspace_id": "ws-1",
        "agent_id": agent_id,
        "genome_hash": "gh",
        "constitution_hash": "ch",
        "plan_hash": "ph",
        "input_hash": "ih",
        "decision_frame_hash": "dfh",
        "governance_decision": "ALLOW",
        "risk_tier": "standard",
        "approved_budget_cents": 1000,
        "reserve_cents": 200,
        "actor_id": "pgl-actor",
        "provenance": {"issuer": "https://cappo.veklom.com", "recorded_by": "cappo-backend"},
    }


def _cappo_post_details(agent_id: str, pre_event_id: str) -> dict:
    # Mirror of GnomledgerPGLAdapter.mint_post_certificate details.
    return {
        "schema_version": "pgl.post_execution_attestation.v1",
        "run_id": "run-1",
        "agent_id": agent_id,
        "pre_authorization_event_id": pre_event_id,
        "output_hash": "oh",
        "outcome_hash": "ch2",
        "governance_decision": "ALLOW",
        "actor_id": "pgl-actor",
        "provenance": {"issuer": "https://cappo.veklom.com", "recorded_by": "cappo-backend"},
        "model_used": "test-provider/test-model",
    }


def test_cappo_pre_and_post_payloads_are_accepted_and_linked(world):
    agent_id = register(world)["agent_id"]

    pre = world["client"].post(
        "/api/v1/ledger/events",
        json={
            "agent_id": agent_id,
            "event_type": "pre_execution_authorization",
            "actor": "cappo-backend",
            "summary": "Execution authorization for run run-1",
            "details": _cappo_pre_details(agent_id),
        },
        headers=world["operator"],
    )
    assert pre.status_code == 201, pre.text
    pre_event_id = pre.json()["event_id"]

    post = world["client"].post(
        "/api/v1/ledger/events",
        json={
            "agent_id": agent_id,
            "event_type": "post_execution_attestation",
            "actor": "cappo-backend",
            "summary": "Execution attestation for run run-1",
            "details": _cappo_post_details(agent_id, pre_event_id),
        },
        headers=world["operator"],
    )
    assert post.status_code == 201, post.text
    body = post.json()
    assert body["details"]["pre_authorization_event_id"] == pre_event_id
    assert body["details"]["model_used"] == "test-provider/test-model"
