"""Agents are generic and disposable: nobody types their names. The server names each one
<OperatorInitials>-<OperatorShortId>-<runSeq> from the authenticated operator, and records
who authorized its run mode. The operator, not the agent, is the accountable party.

Design (2026-10-06, owner): agent_name becomes optional; autonomy is a recorded, named
decision; industry is captured as context.
"""

from __future__ import annotations

import hashlib
import re

import pytest

from app import models

from .audit_support import LEGACY_GENOME, genome, make_world, register, registration

HANDLE = re.compile(r"^[A-Z0-9]{1,3}-[0-9a-f]{8}-(\d+)$")


@pytest.fixture
def world(session):
    world = make_world(session)
    session.add(
        models.User(
            account_id=world["account"].id,
            email="anthony@example.com",
            full_name="Anthony Millwater",
            role="owner",
        )
    )
    session.commit()
    return world


def _unnamed(genome_body=None):
    body = registration(genome_body)
    del body["agent_name"], body["creator"]
    return body


def test_unnamed_registration_gets_a_sequential_operator_handle(world):
    short_id = hashlib.sha256(f"pgl-account:{world['account'].id}".encode()).hexdigest()[:8]
    first, second, third = (register(world, _unnamed()) for _ in range(3))

    assert [a["agent_handle"] for a in (first, second, third)] == [
        f"AM-{short_id}-1",
        f"AM-{short_id}-2",
        f"AM-{short_id}-3",
    ]
    assert first["name"] == first["agent_handle"]
    operator_key = world["session"].query(models.ApiKey).filter_by(role="operator").one()
    assert first["creator"].startswith(f"api_key:{operator_key.id}:")

    detail = world["client"].get(f"/api/v1/agents/{first['agent_id']}", headers=world["viewer"])
    assert detail.json()["agent_handle"] == first["agent_handle"]


def test_named_registration_still_works_and_also_gets_a_handle(world):
    created = register(world, registration(LEGACY_GENOME))

    assert created["name"] == "claims-triage"
    assert created["creator"] == "dana.reyes@example.com"
    assert HANDLE.match(created["agent_handle"])


def test_handle_cannot_be_supplied_by_the_client(world):
    body = _unnamed()
    body["agent_handle"] = "XX-00000000-999"
    created = register(world, body)

    assert created["agent_handle"].startswith("AM-")
    assert HANDLE.match(created["agent_handle"]).group(1) == "1"


def test_each_operator_counts_its_own_runs(world):
    register(world, _unnamed())
    register(world, _unnamed())

    outsider = world["client"].post("/api/v1/agents", json=_unnamed(), headers=world["outsider"])
    assert outsider.status_code == 201
    handle = outsider.json()["agent_handle"]
    assert HANDLE.match(handle).group(1) == "1"
    assert not handle.startswith("AM-")  # initials come from that account, not the caller's input


def test_run_mode_authorization_and_context_are_on_the_certificate(world):
    created = register(world, _unnamed(genome(run_mode="autonomous")))
    document = created["certificate"]["certificate"]
    operator_key = world["session"].query(models.ApiKey).filter_by(role="operator").one()

    assert document["agent_handle"] == created["agent_handle"]
    assert document["accountability"]["registered_by"]["api_key_id"] == operator_key.id
    assert document["run_mode"]["mode"] == "autonomous"
    assert document["run_mode"]["authorized_by"]["api_key_id"] == operator_key.id
    assert document["run_mode"]["authorized_at"] == document["issued_at"]
    assert document["context"] == {
        "industry": "insurance",
        "intended_use": "assist",
        "jurisdiction": "EU",
    }
    birth = world["session"].query(models.LedgerEvent).filter_by(event_type="birth_registration").one()
    assert birth.details["run_mode_authorization"]["mode"] == "autonomous"
    assert birth.details["agent_handle"] == created["agent_handle"]


def test_unset_run_mode_is_reported_as_a_gap(world):
    body = genome()
    del body["run_mode"]
    certificate = register(world, _unnamed(body))["certificate"]

    assert certificate["missing_accountability_fields"] == ["run_mode"]
    assert certificate["certificate"]["run_mode"] == {
        "mode": None,
        "authorized_by": None,
        "authorized_at": None,
    }


def test_switching_to_autonomous_records_who_authorized_it(world):
    agent_id = register(world, _unnamed())["agent_id"]
    response = world["client"].patch(
        f"/api/v1/agents/{agent_id}/genome",
        json={"reason": "approved for unattended runs", "changes": genome(run_mode="autonomous")},
        headers=world["admin"],
    )
    assert response.status_code == 200

    event = world["session"].query(models.LedgerEvent).filter_by(event_type="mutation_update").one()
    admin_key = world["session"].query(models.ApiKey).filter_by(role="admin").one()
    authorization = event.details["run_mode_authorization"]
    assert authorization["mode"] == "autonomous"
    assert authorization["authorized_by"]["api_key_id"] == admin_key.id
    assert event.details["changed_fields"] == ["run_mode"]


def test_bootstrap_records_the_operator_full_name(session):
    from fastapi.testclient import TestClient

    from app.dependencies import get_db
    from app.main import create_app

    app = create_app()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    response = TestClient(app).post(
        "/api/v1/admin/bootstrap",
        json={
            "bootstrap_token": "dev-bootstrap-token",
            "account_name": "Millwater Ops",
            "admin_name": "anthony@example.com",
            "admin_full_name": "Anthony Millwater",
        },
    )
    assert response.status_code == 200, response.text
    assert session.query(models.User).one().full_name == "Anthony Millwater"
