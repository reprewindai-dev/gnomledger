from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import AgentResponse, GenomePayload, LineageTreeNode
from ..utils import short_id


class LineageService:
    def __init__(self, db: Session):
        self.db = db

    def _get_agent_by_public_id(self, agent_id: str) -> models.Agent:
        agent = self.db.execute(
            select(models.Agent).where(models.Agent.agent_id == agent_id)
        ).scalar_one_or_none()
        if not agent:
            raise ValueError("Unknown agent_id")
        return agent

    def fork_agent(self, source_agent_id: str, new_name: str, creator: str, jurisdiction: str) -> AgentResponse:
        source = self._get_agent_by_public_id(source_agent_id)
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
            genome=genome_payload,
            parent_agent_ids=[source.agent_id],
            created_at=new_agent.created_at,
        )

    def _build_tree(self, agent: models.Agent) -> LineageTreeNode:
        children_edges = self.db.execute(
            select(models.LineageEdge).where(models.LineageEdge.parent_agent_id == agent.id)
        ).scalars()
        children_nodes = [self._build_tree(edge.child) for edge in children_edges]
        return LineageTreeNode(agent_id=agent.agent_id, name=agent.name, children=children_nodes)

    def get_tree(self, agent_id: str) -> LineageTreeNode:
        agent = self._get_agent_by_public_id(agent_id)
        return self._build_tree(agent)
