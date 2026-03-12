from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class GenomePayload(BaseModel):
    model_family: str
    model_version: str
    architecture: str
    tools: list[str]
    permissions: list[str]
    safety_rules: list[str]
    runtime_config: dict[str, Any]
    intended_use: str
    risk_category: Literal["low", "medium", "high"]


class AgentCreateRequest(BaseModel):
    account_id: int
    agent_name: str = Field(min_length=1, max_length=255)
    creator: str
    jurisdiction: str
    genome: GenomePayload
    parent_agent_ids: list[str] = Field(default_factory=list)


class AgentResponse(BaseModel):
    agent_id: str
    certificate_id: str
    name: str
    creator: str
    jurisdiction: str
    declared_purpose: str
    status: str
    genome: GenomePayload
    parent_agent_ids: list[str]
    created_at: datetime


class GenomeUpdateRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=255)
    changes: GenomePayload
    note: str = "Genome update"


class LedgerEventCreate(BaseModel):
    agent_id: str
    event_type: Literal[
        "birth_registration",
        "mutation_update",
        "test_audit",
        "deployment",
        "incident",
        "custom",
    ]
    actor: str
    summary: str
    details: dict[str, Any]


class LedgerEventResponse(BaseModel):
    event_id: str
    event_type: str
    actor: str
    summary: str
    details: dict[str, Any]
    prev_event_hash: str | None
    event_hash: str
    created_at: datetime


class LineageTreeNode(BaseModel):
    agent_id: str
    name: str
    children: list["LineageTreeNode"] = Field(default_factory=list)


LineageTreeNode.model_rebuild()


class BillingUsageResponse(BaseModel):
    metric: str
    amount: float
    period_start: datetime
    period_end: datetime


class StripeWebhookPayload(BaseModel):
    id: str
    type: str
    data: dict[str, Any]


class HealthResponse(BaseModel):
    status: Literal["ok", "error"]
    timestamp: datetime


class CertificateDownloadResponse(BaseModel):
    certificate_id: str
    document_uri: HttpUrl | None
