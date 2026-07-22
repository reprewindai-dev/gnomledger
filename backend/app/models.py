from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    tier: Mapped[str] = mapped_column(String(32), default="launch")
    status: Mapped[str] = mapped_column(String(32), default="active")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64))
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    users: Mapped[list["User"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    agents: Mapped[list["Agent"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    billing_usage: Mapped[list["BillingUsage"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="viewer")
    full_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    account: Mapped[Account] = relationship(back_populates="users")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), default="viewer")
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    account: Mapped[Account] = relationship(back_populates="api_keys")

    __table_args__ = (UniqueConstraint("account_id", "name", name="uq_api_key_name"),)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    creator: Mapped[str] = mapped_column(String(255), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(64), nullable=False)
    declared_purpose: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="registered")
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    account: Mapped[Account] = relationship(back_populates="agents")
    genome_versions: Mapped[list["GenomeVersion"]] = relationship(back_populates="agent", cascade="all, delete-orphan")
    certificate: Mapped["BirthCertificate"] = relationship(back_populates="agent", uselist=False, cascade="all, delete-orphan")
    trust_snapshot: Mapped["AgentTrustSnapshot"] = relationship(back_populates="agent", uselist=False, cascade="all, delete-orphan")
    ledger_events: Mapped[list["LedgerEvent"]] = relationship(back_populates="agent", cascade="all, delete-orphan")
    parent_edges: Mapped[list["LineageEdge"]] = relationship(
        back_populates="child", foreign_keys="LineageEdge.child_agent_id", cascade="all, delete-orphan"
    )
    child_edges: Mapped[list["LineageEdge"]] = relationship(
        back_populates="parent", foreign_keys="LineageEdge.parent_agent_id", cascade="all, delete-orphan"
    )
    incidents: Mapped[list["IncidentRecord"]] = relationship(back_populates="agent", cascade="all, delete-orphan")
    audit_reminders: Mapped[list["AuditReminder"]] = relationship(back_populates="agent", cascade="all, delete-orphan")


class GenomeVersion(Base):
    __tablename__ = "genome_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    genome_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    note: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    agent: Mapped[Agent] = relationship(back_populates="genome_versions")

    __table_args__ = (
        UniqueConstraint("agent_id", "version", name="uq_genome_version"),
        CheckConstraint("version > 0", name="ck_genome_version_positive"),
    )


class BirthCertificate(Base):
    __tablename__ = "birth_certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), unique=True, nullable=False)
    certificate_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    genome_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    document_uri: Mapped[str | None] = mapped_column(String(512))
    parent_agent_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    certificate_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    agent: Mapped[Agent] = relationship(back_populates="certificate")


class LedgerEvent(Base):
    __tablename__ = "ledger_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    event_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(String(512), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    prev_event_hash: Mapped[str | None] = mapped_column(String(128))
    event_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    agent: Mapped[Agent] = relationship(back_populates="ledger_events")

    __table_args__ = (
        UniqueConstraint("agent_id", "idempotency_key", name="uq_ledger_idempotency"),
    )


class LineageEdge(Base):
    __tablename__ = "lineage_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    child_agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    parent: Mapped[Agent] = relationship(back_populates="child_edges", foreign_keys=[parent_agent_id])
    child: Mapped[Agent] = relationship(back_populates="parent_edges", foreign_keys=[child_agent_id])

    __table_args__ = (UniqueConstraint("parent_agent_id", "child_agent_id", name="uq_lineage_pair"),)


class BillingUsage(Base):
    __tablename__ = "billing_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    account: Mapped[Account] = relationship(back_populates="billing_usage")


class BillingEvent(Base):
    __tablename__ = "billing_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stripe_event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    account: Mapped[Account | None] = relationship()


# ---------------------------------------------------------------------------
# Migrated from pgl-studioai
# ---------------------------------------------------------------------------

class IncidentRecord(Base):
    """Tracks operational incidents linked to a registered agent."""
    __tablename__ = "incident_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    incident_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False,
        # low | medium | high | critical
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open",
        # open | investigating | resolved | closed
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reporter: Mapped[str] = mapped_column(String(255), nullable=False)
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    agent: Mapped[Agent] = relationship(back_populates="incidents")

    __table_args__ = (
        CheckConstraint("severity IN ('low','medium','high','critical')", name="ck_incident_severity"),
        CheckConstraint("status IN ('open','investigating','resolved','closed')", name="ck_incident_status"),
    )


class AuditReminder(Base):
    """Scheduled audit reminders for registered agents."""
    __tablename__ = "audit_reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    reminder_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    frequency: Mapped[str] = mapped_column(
        String(16), nullable=False,
        # once | daily | weekly | monthly
    )
    next_trigger_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    agent: Mapped[Agent] = relationship(back_populates="audit_reminders")

    __table_args__ = (
        CheckConstraint("frequency IN ('once','daily','weekly','monthly')", name="ck_reminder_frequency"),
    )


class AgentTrustSnapshot(Base):
    __tablename__ = "agent_trust_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), unique=True, nullable=False)
    trust_score: Mapped[float] = mapped_column(default=50.0)
    risk_tier: Mapped[str] = mapped_column(String(32), default="sandbox")
    trust_policy_version: Mapped[str] = mapped_column(String(16), default="v1")
    evidence_head: Mapped[str | None] = mapped_column(String(128), nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    agent: Mapped[Agent] = relationship(back_populates="trust_snapshot")
