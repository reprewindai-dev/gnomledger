from __future__ import annotations

from datetime import timedelta

from app import models
from app.schemas import AgentCreateRequest, GenomePayload, IncidentCreate, IncidentUpdate, AuditReminderCreate
from app.services.certificate_service import CertificateService
from app.services.incident_service import IncidentService
from app.services.reminder_service import ReminderService
from app.utils import short_id, utc_now


def _seed_account(session, tier="launch"):
    account = models.Account(name=f"acct-{short_id('acc')}", tier=tier)
    session.add(account)
    session.flush()
    return account


def _seed_agent(session, account):
    payload = AgentCreateRequest(
        agent_name="seed",
        creator="owner",
        jurisdiction="US",
        genome=GenomePayload(
            model_family="transformer",
            model_version="1",
            architecture="small",
            tools=[],
            permissions=["read"],
            safety_rules=["none"],
            runtime_config={"gpu": "a10"},
            intended_use="assist",
            risk_category="low",
        ),
        parent_agent_ids=[],
    )
    return CertificateService(session).register_agent(payload, account_id=account.id)


def test_create_and_list_incident(session):
    account = _seed_account(session)
    agent = _seed_agent(session, account)

    service = IncidentService(session)
    created = service.create_incident(
        IncidentCreate(
            agent_id=agent.agent_id,
            severity="high",
            title="Unexpected tool call",
            description="Agent called an unauthorized tool",
            reporter="notary-admin@veklom.com",
        )
    )

    assert created.status == "open"
    assert created.agent_id == agent.agent_id
    assert created.resolved_at is None

    listed = service.list_incidents(agent_id=agent.agent_id)
    assert len(listed) == 1
    assert listed[0].incident_id == created.incident_id


def test_update_incident_sets_resolved_at(session):
    account = _seed_account(session)
    agent = _seed_agent(session, account)
    service = IncidentService(session)

    created = service.create_incident(
        IncidentCreate(
            agent_id=agent.agent_id,
            severity="medium",
            title="Budget threshold warning",
            description="Approaching monthly cap",
            reporter="billing-monitor",
        )
    )
    assert created.resolved_at is None

    updated = service.update_incident(
        created.incident_id,
        IncidentUpdate(status="resolved", resolution_notes="Budget increased"),
    )

    assert updated.status == "resolved"
    assert updated.resolution_notes == "Budget increased"
    assert updated.resolved_at is not None


def test_incident_unknown_agent_raises(session):
    service = IncidentService(session)
    try:
        service.create_incident(
            IncidentCreate(
                agent_id="does-not-exist",
                severity="low",
                title="x",
                description="x",
                reporter="x",
            )
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Unknown agent_id" in str(exc)


def test_create_and_list_reminder(session):
    account = _seed_account(session)
    agent = _seed_agent(session, account)
    service = ReminderService(session)

    created = service.create_reminder(
        AuditReminderCreate(
            agent_id=agent.agent_id,
            title="Quarterly compliance review",
            message="Review genome and safety rules",
            frequency="monthly",
            next_trigger_at=utc_now() + timedelta(days=30),
        )
    )

    assert created.is_active is True
    assert created.agent_id == agent.agent_id

    listed = service.list_reminders(agent_id=agent.agent_id)
    assert len(listed) == 1
    assert listed[0].reminder_id == created.reminder_id


def test_delete_reminder(session):
    account = _seed_account(session)
    agent = _seed_agent(session, account)
    service = ReminderService(session)

    created = service.create_reminder(
        AuditReminderCreate(
            agent_id=agent.agent_id,
            title="One-off check",
            message="Verify ledger chain",
            frequency="once",
            next_trigger_at=utc_now() + timedelta(days=1),
        )
    )

    service.delete_reminder(created.reminder_id)
    remaining = service.list_reminders(agent_id=agent.agent_id)
    assert remaining == []


def test_reminder_unknown_agent_raises(session):
    service = ReminderService(session)
    try:
        service.create_reminder(
            AuditReminderCreate(
                agent_id="does-not-exist",
                title="x",
                message="x",
                frequency="once",
                next_trigger_at=utc_now(),
            )
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Unknown agent_id" in str(exc)
