from __future__ import annotations

from app import models
from app.schemas import AgentCreateRequest, GenomePayload, LineageForkRequest
from app.services.certificate_service import CertificateService
from app.services.genome_service import GenomeService
from app.services.lineage_service import LineageService
from app.services.ledger_service import LedgerService
from app.schemas import GenomeUpdateRequest
from app.utils import short_id


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


def test_ledger_idempotency(session):
    account = _seed_account(session)
    created = _seed_agent(session, account)
    svc = LedgerService(session)
    event_payload = {
        "agent_id": created.agent_id,
        "event_type": "deployment",
        "actor": "owner",
        "summary": "deployed",
        "details": {"env": "prod"},
        "idempotency_key": "test-idempotent-1",
    }
    from app.schemas import LedgerEventCreate

    first = svc.log_event(LedgerEventCreate(**event_payload))
    second = svc.log_event(LedgerEventCreate(**event_payload))
    assert first.event_id == second.event_id


def test_lineage_fork_chain(session):
    account = _seed_account(session)
    created = _seed_agent(session, account)
    lineage = LineageService(session)
    forked = lineage.fork_agent(
        account_id=account.id,
        source_agent_id=created.agent_id,
        new_name="child",
        creator="owner",
        jurisdiction="US",
    )
    tree = lineage.get_tree(account.id, created.agent_id)
    assert tree.agent_id == created.agent_id
    assert len(tree.children) == 1
    assert tree.children[0].agent_id == forked.agent_id
