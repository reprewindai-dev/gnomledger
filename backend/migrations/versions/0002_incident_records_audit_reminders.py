"""add incident_records and audit_reminders tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-07
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incident_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("incident_id", sa.String(36), nullable=False, unique=True),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reporter", sa.String(255), nullable=False),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "severity IN ('low','medium','high','critical')",
            name="ck_incident_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open','investigating','resolved','closed')",
            name="ck_incident_status",
        ),
    )
    op.create_index("ix_incident_records_agent_id", "incident_records", ["agent_id"])
    op.create_index("ix_incident_records_status", "incident_records", ["status"])

    op.create_table(
        "audit_reminders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("reminder_id", sa.String(36), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("frequency", sa.String(16), nullable=False),
        sa.Column("next_trigger_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "frequency IN ('once','daily','weekly','monthly')",
            name="ck_reminder_frequency",
        ),
    )
    op.create_index("ix_audit_reminders_agent_id", "audit_reminders", ["agent_id"])
    op.create_index("ix_audit_reminders_next_trigger_at", "audit_reminders", ["next_trigger_at"])


def downgrade() -> None:
    op.drop_table("audit_reminders")
    op.drop_table("incident_records")
