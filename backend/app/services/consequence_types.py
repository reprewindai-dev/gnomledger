# gateway/types.py
# Canonical Pydantic models for the Veklom Sovereign Consequence Authority.
# Six-Part Invariant: Accepted Effect => I ∧ P ∧ A ∧ S ∧ X ∧ E
# Constitution v4.02.1 | Jurisdiction: Canada ISED 'AI for All'

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# I — Identity
# ─────────────────────────────────────────────────────────────────────────────

class WorkloadIdentity(BaseModel):
    """Cryptographically verified workload identity (SPIFFE SVID or OIDC)."""
    principal: str = Field(..., description="SPIFFE URI or OIDC subject claim")
    workspace_id: uuid.UUID
    verified_at: datetime
    ttl_seconds: int = Field(..., gt=0)
    credential_hash: str = Field(..., description="SHA-256 of the raw credential")


# ─────────────────────────────────────────────────────────────────────────────
# P — ActionIntent (input to policy evaluation)
# ─────────────────────────────────────────────────────────────────────────────

class ActionIntent(BaseModel):
    """A structured, well-typed request for a consequential action."""
    intent_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    capability_type: str = Field(..., min_length=1, description="e.g. 'github.patch'")
    target_resource: str = Field(..., min_length=1, description="e.g. 'github.com/org/repo@main'")
    target_expected_version: str = Field(
        ..., min_length=1,
        description="Expected current version for TOCTOU protection"
    )
    max_cost_usd: float = Field(..., gt=0)
    parameters: dict[str, Any] = Field(default_factory=dict)
    manifest_pin_hash: str = Field(..., min_length=64)

    @field_validator("manifest_pin_hash")
    @classmethod
    def must_be_sha256(cls, v: str) -> str:
        if len(v) != 64:
            raise ValueError("manifest_pin_hash must be a 64-char SHA-256 hex string")
        return v


# ─────────────────────────────────────────────────────────────────────────────
# A — CapabilityLease (CAPPO output / Lockerphycer input)
# ─────────────────────────────────────────────────────────────────────────────

class CapabilityLease(BaseModel):
    """Cryptographically signed, short-lived lease granting exact authority."""
    lease_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    workspace_id: uuid.UUID
    principal: str
    capability_type: str
    target_resource: str
    target_expected_version: str = Field(
        ..., description="Locks lease to this exact resource version (TOCTOU)"
    )
    expires_at: datetime
    max_cost_usd: float
    policy_hash: str = Field(..., description="SHA-256 of the SEKED policy set")
    signature: str = Field(..., description="Ed25519 signature over canonical fields")
    delegation_depth: int = Field(0, ge=0, le=2)
    receipt_required: bool = True

    def is_expired(self) -> bool:
        from datetime import timezone
        return datetime.now(tz=timezone.utc) >= self.expires_at


# ─────────────────────────────────────────────────────────────────────────────
# S — Target-State precondition
# ─────────────────────────────────────────────────────────────────────────────

class TargetStateCheck(BaseModel):
    resource: str
    expected_version: str
    actual_version: str
    matched: bool


# ─────────────────────────────────────────────────────────────────────────────
# X — ExecutionCellReceipt (Lockerphycer output)
# ─────────────────────────────────────────────────────────────────────────────

class EgressAttempt(BaseModel):
    destination: str
    blocked: bool
    timestamp: datetime


class ExecutionCellReceipt(BaseModel):
    cell_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    lease_id: uuid.UUID
    workspace_id: uuid.UUID
    started_at: datetime
    terminated_at: datetime
    wall_time_ms: int
    cpu_millicore_seconds: int
    ram_mib_peak: int
    output_artifact_hash: str
    egress_attempts: list[EgressAttempt] = Field(default_factory=list)
    exit_code: int


# ─────────────────────────────────────────────────────────────────────────────
# E — ExecutionReceipt (GnomLedger anchor — the final proof)
# ─────────────────────────────────────────────────────────────────────────────

class ExecutionOutcome(str, Enum):
    SUCCESS              = "SUCCESS"
    FAILED_PRECONDITION  = "FAILED_PRECONDITION"
    FAILED_POLICY        = "FAILED_POLICY"
    FAILED_EXECUTION     = "FAILED_EXECUTION"
    FAILED_EVIDENCE      = "FAILED_EVIDENCE"


class ExecutionReceipt(BaseModel):
    """
    The canonical, immutable, tamper-evident record of a governed execution.
    WHO + WHAT + WHY + WHERE + WHEN + STATE_BEFORE + STATE_AFTER +
    HOW_MUCH + OUTCOME + PROOF
    """
    receipt_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    # WHO
    principal: str
    workspace_id: uuid.UUID
    # WHAT / WHY
    capability_type: str
    action_intent_id: uuid.UUID
    # UNDER WHAT AUTHORITY
    lease_id: uuid.UUID
    policy_hash: str
    # WHERE
    target_resource: str
    sovereign_region: str = "ca-central-1"
    # WHEN
    executed_at: datetime
    # STATE BEFORE / AFTER
    state_before_version: str
    state_after_version: str
    # HOW MUCH
    cost_usd: float
    x402_settlement_id: Optional[str] = None
    # OUTCOME
    outcome: ExecutionOutcome
    error_message: Optional[str] = None
    # PROOF
    cell_receipt_hash: str
    signature: str
    previous_receipt_hash: str


# ─────────────────────────────────────────────────────────────────────────────
# Policy
# ─────────────────────────────────────────────────────────────────────────────

class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY  = "DENY"


class PolicyEvaluationResult(BaseModel):
    decision: PolicyDecision
    reason: str
    policy_hash: str
    evaluated_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# API envelopes
# ─────────────────────────────────────────────────────────────────────────────

class VerifyIdentityRequest(BaseModel):
    credential: str = Field(..., description="Raw SPIFFE SVID or OIDC JWT")
    manifest_pin_hash: str

class VerifyIdentityResponse(BaseModel):
    identity: WorkloadIdentity

class CompileContextRequest(BaseModel):
    identity: WorkloadIdentity
    action_intent: ActionIntent

class CompileContextResponse(BaseModel):
    validated_intent: ActionIntent
    context_hash: str

class EvaluatePolicyRequest(BaseModel):
    identity: WorkloadIdentity
    intent: ActionIntent

class EvaluatePolicyResponse(BaseModel):
    result: PolicyEvaluationResult

class IssueLeaseRequest(BaseModel):
    identity: WorkloadIdentity
    intent: ActionIntent
    policy_result: PolicyEvaluationResult

class IssueLeaseResponse(BaseModel):
    lease: CapabilityLease

class SpawnCellRequest(BaseModel):
    lease: CapabilityLease
    workload_image_hash: str

class SpawnCellResponse(BaseModel):
    cell_id: uuid.UUID
    cell_receipt: ExecutionCellReceipt

class RecordEvidenceRequest(BaseModel):
    receipt: ExecutionReceipt

class RecordEvidenceResponse(BaseModel):
    merkle_proof: str
    ledger_sequence: int
