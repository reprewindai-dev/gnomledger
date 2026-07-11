from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PGLRequestContext(BaseModel):
    account_id: int
    api_key_id: int
    role: str


class GenomePayload(BaseModel):
    model_family: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=64)
    architecture: str = Field(min_length=1, max_length=128)
    tools: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    safety_rules: list[str] = Field(default_factory=list)
    runtime_config: dict[str, Any] = Field(default_factory=dict)
    intended_use: str = Field(min_length=1, max_length=255)
    risk_category: Literal["low", "medium", "high", "critical"]


class AgentCreateRequest(BaseModel):
    agent_name: str = Field(min_length=1, max_length=255)
    creator: str = Field(min_length=1, max_length=255)
    jurisdiction: str = Field(min_length=1, max_length=64)
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


class AgentDetailResponse(AgentResponse):
    certificate_uri: str | None
    version_count: int
    latest_genome_hash: str


class GenomeUpdateRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=255)
    changes: GenomePayload
    note: str = "Genome update"


class LedgerEventCreate(BaseModel):
    agent_id: str = Field(min_length=1, max_length=36)
    event_type: Literal[
        "birth_registration",
        "mutation_update",
        "test_audit",
        "deployment",
        "incident",
        "custom",
        "birth",
        "audit",
        "genome_update",
    ]
    actor: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1, max_length=255)
    details: dict[str, Any]
    idempotency_key: str | None = None


class LedgerEventResponse(BaseModel):
    event_id: str
    event_type: str
    actor: str
    summary: str
    details: dict[str, Any]
    prev_event_hash: str | None
    event_hash: str
    created_at: datetime


class LedgerChainVerifyRequest(BaseModel):
    valid: bool
    latest_event_hash: str | None
    checked_events: int
    first_event_at: datetime | None
    last_event_at: datetime | None
    errors: list[str] = Field(default_factory=list)


class LineageTreeNode(BaseModel):
    agent_id: str
    name: str
    status: str
    children: list["LineageTreeNode"] = Field(default_factory=list)


LineageTreeNode.model_rebuild()


class LineageForkRequest(BaseModel):
    source_agent_id: str = Field(min_length=1, max_length=36)
    new_name: str = Field(min_length=1, max_length=255)
    creator: str = Field(min_length=1, max_length=255)
    jurisdiction: str = Field(min_length=1, max_length=64)


class BillingUsageResponse(BaseModel):
    metric: str
    amount: float
    period_start: datetime
    period_end: datetime


class BillingUsageRequest(BaseModel):
    metric: str = Field(min_length=1, max_length=64)
    amount: float = Field(ge=0)


class StripeWebhookPayload(BaseModel):
    id: str
    type: str
    data: dict[str, Any]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    timestamp: datetime


class CertificateDownloadResponse(BaseModel):
    certificate_id: str
    document_uri: str | None
    issued_at: datetime


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    role: str = Field(default="viewer", min_length=1, max_length=32)
    scopes: list[str] = Field(default_factory=list)
    account_id: int | None = None


class ApiKeyCreateResponse(BaseModel):
    api_key: str
    api_key_prefix: str
    account_id: int
    role: str
    scopes: list[str]


class ApiKeyListItem(BaseModel):
    id: int
    account_id: int
    name: str
    key_prefix: str
    role: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    expires_at: datetime | None


class BootstrapRequest(BaseModel):
    bootstrap_token: str = Field(min_length=1)
    account_name: str = Field(min_length=1, max_length=255)
    account_tier: Literal["free", "launch", "scale", "enterprise"] = "free"
    admin_name: str = Field(default="genome-ledger-admin", max_length=255)


class ErrorResponse(BaseModel):
    detail: str


class UsageLimitResponse(BaseModel):
    account_id: int
    metric: str
    used: float
    limit: float
    remaining: float


class AdapterUsageLimitResponse(BaseModel):
    metric: str
    used: float
    limit: float
    remaining: float


class VeklmAdapterSnapshot(BaseModel):
    adapter: Literal["vekml"]
    exported_at: datetime
    account_id: int
    agent: AgentDetailResponse
    certificate: CertificateDownloadResponse
    ledger_events: list[LedgerEventResponse]
    chain_verification: LedgerChainVerifyRequest
    lineage: LineageTreeNode
    usage_limits: list[AdapterUsageLimitResponse]
    snapshot_hash: str


class IncidentCreate(BaseModel):
    agent_id: str
    severity: Literal["low", "medium", "high", "critical"]
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    reporter: str = Field(min_length=1, max_length=255)


class IncidentResponse(BaseModel):
    incident_id: str
    agent_id: str
    severity: Literal["low", "medium", "high", "critical"]
    status: Literal["open", "investigating", "resolved", "closed"]
    title: str
    description: str
    reporter: str
    resolution_notes: str | None
    created_at: datetime
    resolved_at: datetime | None


class IncidentUpdate(BaseModel):
    status: Literal["open", "investigating", "resolved", "closed"]
    resolution_notes: str | None = None


class AuditReminderCreate(BaseModel):
    agent_id: str
    title: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1)
    frequency: Literal["once", "daily", "weekly", "monthly"]
    next_trigger_at: datetime


class AuditReminderResponse(BaseModel):
    reminder_id: str
    agent_id: str
    title: str
    message: str
    frequency: Literal["once", "daily", "weekly", "monthly"]
    next_trigger_at: datetime
    last_triggered_at: datetime | None
    is_active: bool
    created_at: datetime
