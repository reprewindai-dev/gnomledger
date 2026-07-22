from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import AgentResponse, GenomePayload, LineageTreeNode
from .billing_service import BillingService
from ..utils import short_id


class LineageService:
    def __init__(self, db: Session):
        self.db = db
        self.billing_service = BillingService(db)

    def _get_agent_by_public_id(self, account_id: int, agent_id: str) -> models.Agent:
        agent = self.db.execute(
            select(models.Agent).where(
                models.Agent.account_id == account_id, models.Agent.agent_id == agent_id
            )
        ).scalar_one_or_none()
        if not agent:
            raise ValueError("Unknown agent_id")
        return agent

    def fork_agent(
        self,
        account_id: int,
        source_agent_id: str,
        new_name: str,
        creator: str,
        jurisdiction: str,
    ) -> AgentResponse:
        source = self._get_agent_by_public_id(account_id, source_agent_id)

        latest_genome = (
            self.db.execute(
                select(models.GenomeVersion)
                .where(models.GenomeVersion.agent_id == source.id)
                .order_by(models.GenomeVersion.version.desc())
                .limit(1)
            )
        ).scalar_one()

        new_agent_id = short_id("agent")
        new_certificate_id = short_id("cert")

        new_agent = models.Agent(
            account_id=source.account_id,
            agent_id=new_agent_id,
            name=new_name,
            creator=creator,
            jurisdiction=jurisdiction,
            declared_purpose=source.declared_purpose,
        )
        self.db.add(new_agent)
        self.db.flush()

        # Ensure no cycle by validating edge insertion against account boundaries
        if source.account_id != new_agent.account_id:
            raise ValueError("Cross-account lineage is not permitted")

        new_genome = models.GenomeVersion(
            agent_id=new_agent.id,
            version=1,
            payload=latest_genome.payload,
            genome_hash=latest_genome.genome_hash,
            note="Forked from parent",
        )
        certificate = models.BirthCertificate(
            agent_id=new_agent.id,
            certificate_id=new_certificate_id,
            genome_hash=latest_genome.genome_hash,
            parent_agent_ids=[source.agent_id],
        )
        edge = models.LineageEdge(parent_agent_id=source.id, child_agent_id=new_agent.id)

        self.db.add_all([new_genome, certificate, edge])

        # Recalculate trust snapshot and save to DB in same transaction
        from .trust_policy import TrustPolicyV1
        from ..utils import utc_now
        trust_data = TrustPolicyV1.calculate_trust([])
        
        snapshot = models.AgentTrustSnapshot(
            agent_id=new_agent.id,
            trust_score=trust_data["trust_score"],
            risk_tier=trust_data["risk_tier"],
            trust_policy_version=trust_data["trust_policy_version"],
            evidence_head=trust_data["evidence_head"],
            calculated_at=utc_now()
        )
        self.db.add(snapshot)
        new_agent.trust_snapshot = snapshot

        self.db.commit()
        self.db.refresh(new_agent)

        genome_payload = GenomePayload(**latest_genome.payload)
        return AgentResponse(
            agent_id=new_agent.agent_id,
            certificate_id=certificate.certificate_id,
            name=new_agent.name,
            creator=new_agent.creator,
            jurisdiction=new_agent.jurisdiction,
            declared_purpose=new_agent.declared_purpose,
            status=new_agent.status,
            trust_score=snapshot.trust_score,
            risk_tier=snapshot.risk_tier,
            trust_policy_version=snapshot.trust_policy_version,
            evidence_head=snapshot.evidence_head,
            genome=genome_payload,
            parent_agent_ids=[source.agent_id],
            created_at=new_agent.created_at,
        )

    def _build_tree(self, agent: models.Agent, visited: set[int] | None = None) -> LineageTreeNode:
        if visited is None:
            visited = set()
        if agent.id in visited:
            return LineageTreeNode(agent_id=agent.agent_id, name=agent.name, status="cycle_blocked", children=[])
        visited.add(agent.id)

        children_edges = self.db.execute(
            select(models.LineageEdge).where(models.LineageEdge.parent_agent_id == agent.id)
        ).scalars()
        children_nodes = [self._build_tree(edge.child, set(visited)) for edge in children_edges]
        return LineageTreeNode(
            agent_id=agent.agent_id,
            name=agent.name,
            status=agent.status,
            children=children_nodes,
        )

    def get_tree(self, account_id: int, agent_id: str, count_usage: bool = True) -> LineageTreeNode:
        agent = self._get_agent_by_public_id(account_id, agent_id)
        if count_usage:
            account = self.db.get(models.Account, account_id)
            if account is None:
                raise ValueError("Unknown account")
            limit = self.billing_service.plan_limit(account=account, metric="lineage_render")
            self.billing_service.ensure_or_raise(account_id=account.id, metric="lineage_render", limit=limit)
            self.billing_service.record_usage(account.id, "lineage_render", 1.0)
        return self._build_tree(agent)
