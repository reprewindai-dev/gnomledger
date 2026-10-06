"""Ledger records are retained: deleting an agent or account no longer cascades to its ledger
events, genome versions or certificate, and decommissioning replaces deletion.

Audit (2026-10-06): Account.agents and Agent.ledger_events / genome_versions / certificate
were "all, delete-orphan", so one ORM delete erased an agent's whole evidence trail.
"""

from __future__ import annotations

import pytest

from app import models
from app.models import RetentionViolation

from .audit_support import LEGACY_GENOME, make_world, register


@pytest.fixture
def world(session):
    world = make_world(session)
    world["agent"] = register(world)
    world["agent_id"] = world["agent"]["agent_id"]
    return world


def _decommission(world, body=None, key="operator"):
    return world["client"].post(
        f"/api/v1/agents/{world['agent_id']}/decommission",
        json=body if body is not None else {"reason": "Replaced by claims-triage-v2"},
        headers=world[key],
    )


def _counts(session):
    return (
        session.query(models.LedgerEvent).count(),
        session.query(models.GenomeVersion).count(),
        session.query(models.BirthCertificate).count(),
        session.query(models.CertificateSignature).count(),
    )


def test_decommission_keeps_every_record_and_appends_a_signed_off_event(world):
    client, session = world["client"], world["session"]
    before_events, versions, certificates, signatures = _counts(session)

    response = _decommission(world, {"reason": "Replaced by v2", "actor": "CRO"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "decommissioned"
    assert body["retained"] == {
        "ledger_events": before_events + 1,
        "genome_versions": versions,
        "birth_certificates": certificates,
    }

    assert _counts(session) == (before_events + 1, versions, certificates, signatures)
    history = client.get(f"/api/v1/ledger/agents/{world['agent_id']}", headers=world["viewer"])
    last = history.json()[-1]
    operator_key = session.query(models.ApiKey).filter_by(role="operator").one()
    assert last["event_type"] == "decommission"
    assert last["event_id"] == body["event_id"]
    assert last["details"]["reason"] == "Replaced by v2"
    assert last["details"]["declared_actor"] == "CRO"
    assert last["details"]["decommissioned_by"]["api_key_id"] == operator_key.id
    assert last["details"]["previous_status"] == "registered"
    verify = client.get(f"/api/v1/ledger/agents/{world['agent_id']}/verify", headers=world["viewer"])
    assert verify.json()["status"] == "verified"
    detail = client.get(f"/api/v1/agents/{world['agent_id']}", headers=world["viewer"])
    assert detail.json()["status"] == "decommissioned"


def test_decommissioned_agent_cannot_change_run_or_be_decommissioned_again(world):
    client, session = world["client"], world["session"]
    genome_hash = session.query(models.GenomeVersion).one().genome_hash
    assert _decommission(world).status_code == 200

    patch = client.patch(
        f"/api/v1/agents/{world['agent_id']}/genome",
        json={"reason": "after the fact", "changes": {**LEGACY_GENOME, "model_version": "9"}},
        headers=world["operator"],
    )
    assert patch.status_code == 409
    assert session.query(models.GenomeVersion).count() == 1

    validate = client.post(
        "/api/v1/agents/execution/validate",
        json={
            "agent_id": world["agent_id"],
            "workspace_id": "ws",
            "requested_tools": [],
            "expected_genome_hash": genome_hash,
        },
        headers=world["operator"],
    )
    assert validate.json()["allowed"] is False
    assert _decommission(world).status_code == 409


@pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "   "}])
def test_decommission_requires_a_reason(world, body):
    assert _decommission(world, body).status_code == 422
    assert world["session"].query(models.Agent).one().status == "registered"


def test_decommission_is_role_checked_and_account_scoped(world):
    assert _decommission(world, key="viewer").status_code == 403
    assert _decommission(world, key="outsider").status_code == 404
    assert world["session"].query(models.Agent).one().status == "registered"


def test_decommission_events_cannot_be_forged_through_the_event_api(world):
    response = world["client"].post(
        "/api/v1/ledger/events",
        json={
            "agent_id": world["agent_id"],
            "event_type": "decommission",
            "actor": "someone",
            "summary": "fake",
            "details": {},
        },
        headers=world["operator"],
    )
    assert response.status_code == 400
    assert world["session"].query(models.Agent).one().status == "registered"


def test_orm_deletes_of_retained_records_are_refused(world):
    session = world["session"]
    before = _counts(session)

    for model in (models.Agent, models.LedgerEvent, models.GenomeVersion, models.BirthCertificate):
        session.delete(session.query(model).first())
        with pytest.raises(RetentionViolation):
            session.flush()
        session.rollback()

    session.delete(session.get(models.Account, world["account"].id))
    with pytest.raises(RetentionViolation, match="registered agents"):
        session.flush()
    session.rollback()

    assert _counts(session) == before
    assert session.query(models.Agent).count() == 1


def test_orm_rewrites_of_ledger_events_and_genome_versions_are_refused(world):
    session = world["session"]
    event = session.query(models.LedgerEvent).first()
    event.details = {"rewritten": True}
    with pytest.raises(RetentionViolation, match="append-only"):
        session.flush()
    session.rollback()

    version = session.query(models.GenomeVersion).first()
    version.note = "rewritten"
    with pytest.raises(RetentionViolation, match="append-only"):
        session.flush()
    session.rollback()


def test_account_without_agents_can_still_be_deleted(session):
    account = models.Account(name="empty-account", tier="launch")
    session.add(account)
    session.commit()

    session.delete(account)
    session.commit()

    assert session.query(models.Account).filter_by(name="empty-account").count() == 0
