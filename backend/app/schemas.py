from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class PGLRequestContext(BaseModel):
    account_id: int
    api_key_id: int
    role: str


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,64}$")
_IMAGE_DIGEST_RE = re.compile(r"^(?:[^@\s]+@)?sha256:[0-9a-f]{64}$")
# A CAPPO capability package ref, e.g. "veklom.governed-counter@v1".
_CAPABILITY_REF_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}@[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$"
)

MIN_LOG_RETENTION_DAYS = 180
LOG_RETENTION_REASON = (
    "log_retention_days must be at least 180. The 180-day default reflects the six-month "
    "minimum that EU AI Act Article 19 sets for logs of high-risk AI systems; this ledger does "
    "not accept a shorter declared retention."
)

DataCategory = Literal[
    "none", "personal", "special_category", "financial", "health", "credentials", "public"
]
RegulatoryRiskClass = Literal["prohibited", "high_risk", "limited", "minimal", "unassessed"]
UseStatement = Annotated[str, Field(min_length=1, max_length=1024)]


class AccountableOwner(BaseModel):
    """The named person answerable for the agent."""

    name: str = Field(min_length=1, max_length=255)
    role: str | None = Field(default=None, max_length=128)
    email: str | None = Field(default=None, max_length=254)
    organization: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        if value is not None and not _EMAIL_RE.match(value):
            raise ValueError("accountable_owner.email must be an email address")
        return value


class OversightPlan(BaseModel):
    """How a human stops or escalates the agent."""

    stop_mechanism: str | None = Field(default=None, max_length=255)
    oversight_contact: str | None = Field(default=None, max_length=255)
    escalation_path: str | None = Field(default=None, max_length=1024)


# Fields the genome had before the accountability fields were added. A genome hash is the
# SHA-256 of the canonical genome (see GenomePayload.canonical), and the canonical form omits
# every newer field left at its default, so genomes registered in the old shape keep the
# exact hash they had.
LEGACY_GENOME_FIELDS = (
    "model_family",
    "model_version",
    "architecture",
    "tools",
    "permissions",
    "safety_rules",
    "runtime_config",
    "intended_use",
    "risk_category",
)


class GenomePayload(BaseModel):
    model_family: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=64)
    architecture: str = Field(min_length=1, max_length=128)
    tools: list[str] = Field(default_factory=list)
    # Declarative only: CAPPO enforces capability_refs, not these strings.
    permissions: list[str] = Field(default_factory=list)
    safety_rules: list[str] = Field(default_factory=list)
    runtime_config: dict[str, Any] = Field(default_factory=dict)
    intended_use: str = Field(min_length=1, max_length=255)
    risk_category: Literal["low", "medium", "high"]

    # -- accountability ----------------------------------------------------------------------
    accountable_owner: AccountableOwner | None = None
    incident_contact: str | None = Field(default=None, max_length=512)
    deployer: str | None = Field(default=None, max_length=255)  # EU AI Act "deployer"
    provider: str | None = Field(default=None, max_length=255)  # EU AI Act "provider"
    model_provider: str | None = Field(default=None, max_length=128)
    model_identifier: str | None = Field(default=None, max_length=512)

    # -- bounded use -------------------------------------------------------------------------
    out_of_scope_uses: list[UseStatement] = Field(default_factory=list, max_length=100)
    known_limitations: list[UseStatement] = Field(default_factory=list, max_length=100)
    data_categories: list[DataCategory] = Field(default_factory=list)
    log_retention_days: int = MIN_LOG_RETENTION_DAYS
    regulatory_risk_class: RegulatoryRiskClass = "unassessed"
    risk_rationale: str | None = Field(default=None, max_length=2000)

    # -- human oversight ---------------------------------------------------------------------
    oversight: OversightPlan | None = None

    # -- enforceable authority ---------------------------------------------------------------
    capability_refs: list[str] = Field(default_factory=list, max_length=100)

    # -- configuration integrity (digests only; prompt text is never accepted) ---------------
    system_prompt_sha256: str | None = None
    code_commit: str | None = None
    image_digest: str | None = Field(default=None, max_length=512)
    tool_versions: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _refuse_prompt_text(cls, data: Any) -> Any:
        if isinstance(data, dict) and "system_prompt" in data:
            raise ValueError(
                "system_prompt text is not accepted; send system_prompt_sha256 (hex SHA-256 "
                "of the prompt). The ledger stores the digest, never the prompt."
            )
        return data

    @field_validator("incident_contact")
    @classmethod
    def _incident_contact(cls, value: str | None) -> str | None:
        if value is not None and not (_EMAIL_RE.match(value) or _URL_RE.match(value)):
            raise ValueError("incident_contact must be an email address or an http(s) URL")
        return value

    @field_validator("log_retention_days")
    @classmethod
    def _retention(cls, value: int) -> int:
        if value < MIN_LOG_RETENTION_DAYS:
            raise ValueError(LOG_RETENTION_REASON)
        if value > 36500:
            raise ValueError("log_retention_days must be at most 36500")
        return value

    @field_validator("data_categories")
    @classmethod
    def _data_categories(cls, value: list[str]) -> list[str]:
        if "none" in value and len(set(value)) > 1:
            raise ValueError("data_categories 'none' cannot be combined with other categories")
        return sorted(set(value))

    @field_validator("capability_refs")
    @classmethod
    def _capability_refs(cls, value: list[str]) -> list[str]:
        for ref in value:
            if not _CAPABILITY_REF_RE.match(ref):
                raise ValueError(
                    f"capability_refs entry {ref!r} is not a capability package ref "
                    "like 'veklom.governed-counter@v1'"
                )
        return sorted(set(value))

    @field_validator("system_prompt_sha256")
    @classmethod
    def _prompt_digest(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if not _SHA256_HEX_RE.match(value):
            raise ValueError("system_prompt_sha256 must be 64 hex characters")
        return value

    @field_validator("code_commit")
    @classmethod
    def _commit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if not _COMMIT_RE.match(value):
            raise ValueError("code_commit must be 7-64 hex characters")
        return value

    @field_validator("image_digest")
    @classmethod
    def _image_digest(cls, value: str | None) -> str | None:
        if value is not None and not _IMAGE_DIGEST_RE.match(value):
            raise ValueError("image_digest must be 'sha256:<64 hex>', optionally after 'repo@'")
        return value

    @field_validator("tool_versions")
    @classmethod
    def _tool_versions(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 200:
            raise ValueError("tool_versions accepts at most 200 entries")
        for name, version in value.items():
            if not name or len(name) > 128 or not version or len(version) > 128:
                raise ValueError("tool_versions names and versions must be 1-128 characters")
        return value

    def canonical(self) -> dict[str, Any]:
        """The stored and hashed form: newer fields left at their defaults are omitted."""
        dumped = self.model_dump()
        canonical: dict[str, Any] = {}
        for name, field in GenomePayload.model_fields.items():
            value = dumped[name]
            if name not in LEGACY_GENOME_FIELDS:
                if value == field.get_default(call_default_factory=True):
                    continue
                if isinstance(value, dict) and name in ("accountable_owner", "oversight"):
                    value = {k: v for k, v in value.items() if v is not None}
            canonical[name] = value
        return canonical


# Accountability fields the certificate reports as missing when absent, so an auditor sees
# the gap instead of silence. A missing block is reported once, not once per member.
ACCOUNTABILITY_FIELDS = (
    "accountable_owner",
    "accountable_owner.role",
    "accountable_owner.email",
    "accountable_owner.organization",
    "incident_contact",
    "deployer",
    "provider",
    "model_provider",
    "model_identifier",
    "out_of_scope_uses",
    "known_limitations",
    "data_categories",
    "regulatory_risk_class",
    "risk_rationale",
    "oversight",
    "oversight.stop_mechanism",
    "oversight.oversight_contact",
    "oversight.escalation_path",
    "capability_refs",
)
INTEGRITY_FIELDS = ("system_prompt_sha256", "code_commit", "image_digest", "tool_versions")


def _is_missing(genome: GenomePayload, path: str) -> bool:
    head, _, member = path.partition(".")
    value = getattr(genome, head)
    if member:
        return value is not None and getattr(value, member) in (None, "")
    if head == "regulatory_risk_class":
        return value == "unassessed"
    return value in (None, "", [], {})


def missing_accountability_fields(genome: GenomePayload) -> list[str]:
    return [path for path in ACCOUNTABILITY_FIELDS if _is_missing(genome, path)]


def missing_integrity_fields(genome: GenomePayload) -> list[str]:
    return [path for path in INTEGRITY_FIELDS if _is_missing(genome, path)]


class AgentCreateRequest(BaseModel):
    agent_name: str = Field(min_length=1, max_length=255)
    creator: str = Field(min_length=1, max_length=255)
    jurisdiction: str = Field(min_length=1, max_length=64)
    genome: GenomePayload
    parent_agent_ids: list[str] = Field(default_factory=list)


class StandardComplianceResult(BaseModel):
    id: str
    version: str | None = None
    result: Literal["PASS", "FAIL", "NOT_EVALUATED", "NOT_FOUND"]
    reason: str | None = None


class PreExecutionAuthorizationDetails(BaseModel):
    schema_version: Literal["pgl.pre_execution_authorization.v1"]
    run_id: str
    workspace_id: str
    agent_id: str
    genome_hash: str
    constitution_hash: str
    plan_hash: str
    input_hash: str | None
    decision_frame_hash: str | None
    governance_decision: str
    risk_tier: str
    approved_budget_cents: int
    reserve_cents: int
    actor_id: str | None
    provenance: dict[str, Any]
    standards_compliance: list[StandardComplianceResult] = Field(default_factory=list)


class PostExecutionAttestationDetails(BaseModel):
    schema_version: Literal["pgl.post_execution_attestation.v1"]
    run_id: str
    agent_id: str
    pre_authorization_event_id: str
    output_hash: str
    outcome_hash: str
    governance_decision: str
    actor_id: str | None
    provenance: dict[str, Any]
    standards_compliance: list[StandardComplianceResult] = Field(default_factory=list)


class AgentResponse(BaseModel):
    agent_id: str
    certificate_id: str
    name: str
    creator: str
    jurisdiction: str
    declared_purpose: str
    status: str
    trust_score: float
    risk_tier: str
    trust_policy_version: str = "v1"
    evidence_head: str | None
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
        "violation",
        "pre_execution_authorization",
        "post_execution_attestation",
        "custom",
    ]
    actor: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1, max_length=255)
    details: dict[str, Any]
    idempotency_key: str | None = None

    @model_validator(mode="after")
    def validate_execution_details(self) -> LedgerEventCreate:
        if self.event_type == "pre_execution_authorization":
            PreExecutionAuthorizationDetails(**self.details)
        elif self.event_type == "post_execution_attestation":
            PostExecutionAttestationDetails(**self.details)
        return self


class LedgerEventResponse(BaseModel):
    event_id: str
    event_type: str
    actor: str
    summary: str
    details: dict[str, Any]
    prev_event_hash: str | None
    event_hash: str
    created_at: datetime
    persisted: bool = True
    idempotent_replay: bool = False
    chain_head: str | None = None


class LedgerChainVerifyRequest(BaseModel):
    status: Literal["verified", "unmeasured", "blocked"]
    valid: bool | None
    latest_event_hash: str | None
    checked_events: int
    first_event_at: datetime | None
    last_event_at: datetime | None
    errors: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=255)


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
    database: Literal["ready", "initializing", "unavailable"] | None = None
    detail: str | None = None


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
    account_tier: Literal["launch", "scale", "enterprise"] = "launch"
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


class ExecutionValidateRequest(BaseModel):
    agent_id: str
    workspace_id: str
    requested_tools: list[str]
    expected_genome_hash: str


class ExecutionValidateResponse(BaseModel):
    allowed: bool
    agent_certificate_id: str | None
    canonical_genome_hash: str | None
    trust_score: float
    risk_tier: str
    trust_policy_version: str
    evidence_head: str | None
