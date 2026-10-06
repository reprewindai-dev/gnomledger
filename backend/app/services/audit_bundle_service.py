"""The audit bundle: one signed JSON document with everything an auditor needs to check an
agent without access to this service's database."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import GenomePayload, LedgerChainVerifyRequest, LedgerEventResponse
from ..utils import canonical_timestamp, stable_hash, utc_now
from .agent_handle import handle_for
from .certificate_service import RETENTION_STATEMENT, certificate_view
from .ledger_service import LedgerService
from .signing_service import ISSUER, get_signer

AUDIT_BUNDLE_SCHEMA_VERSION = "pgl.audit_bundle.v1"

# Stated in every bundle so a reader does not assume more than the ledger proves.
LIMITATIONS = [
    "Ledger events are hash-chained and covered by signed checkpoints, but are not "
    "individually signed.",
    "No external RFC 3161 timestamp or third-party witness anchors the checkpoints; a "
    "checkpoint proves extension only to a party that kept an earlier copy.",
    "Signatures verify against the ledger's current key only; key rotation history is not "
    "published.",
    "Declared fields (owner, limits, permissions, data categories) are the registrant's "
    "statements; the ledger does not verify them. capability_refs are enforced by CAPPO, "
    "not by this ledger.",
    "Retention guards cover ORM deletes and rewrites; direct database access can still "
    "delete rows, which checkpoints held outside the ledger will expose.",
]


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


class AuditBundleService:
    def __init__(self, db: Session):
        self.db = db
        self.ledger = LedgerService(db)

    def build(
        self, agent_id: str, *, account_id: int, generated_by: dict[str, Any]
    ) -> dict[str, Any]:
        agent = self.ledger._resolve_agent(agent_id, account_id)  # foreign agent: ValueError
        signer = get_signer()

        versions = list(
            self.db.execute(
                select(models.GenomeVersion)
                .where(models.GenomeVersion.agent_id == agent.id)
                .order_by(models.GenomeVersion.version.asc())
                .execution_options(populate_existing=True)
            ).scalars()
        )
        hash_mismatches = [v.version for v in versions if stable_hash(v.payload) != v.genome_hash]

        certificate = agent.certificate
        cert_view = certificate_view(self.db, certificate) if certificate else None
        certificate_signature_valid = None
        if cert_view is not None and cert_view.signature is not None:
            certificate_signature_valid = signer.verify(
                cert_view.certificate, cert_view.signature.model_dump()
            )

        events = self.ledger.chain_events(agent)
        _, chain = self.ledger.verify_chain(agent.agent_id, account_id=account_id)
        checkpoint = self.ledger.issue_checkpoint(agent.agent_id, account_id=account_id)
        latest = GenomePayload(**versions[-1].payload) if versions else None

        bundle: dict[str, Any] = {
            "schema_version": AUDIT_BUNDLE_SCHEMA_VERSION,
            "issuer": ISSUER,
            "key_id": signer.key_id,
            "generated_at": utc_now().isoformat(),
            "generated_by": generated_by,
            "agent": {
                "agent_id": agent.agent_id,
                "agent_handle": handle_for(self.db, agent.agent_id),
                "name": agent.name,
                "creator": agent.creator,
                "jurisdiction": agent.jurisdiction,
                "declared_purpose": agent.declared_purpose,
                "status": agent.status,
                "workspace_id": agent.workspace_id,
                "created_at": _iso(agent.created_at),
                "updated_at": _iso(agent.updated_at),
                "parent_agent_ids": list(certificate.parent_agent_ids or []) if certificate else [],
            },
            "genome_versions": [
                {
                    "version": v.version,
                    "genome_hash": v.genome_hash,
                    "note": v.note,
                    "created_at": _iso(v.created_at),
                    "payload": v.payload,
                }
                for v in versions
            ],
            "certificate": cert_view.model_dump(mode="json") if cert_view else None,
            "events": [
                {
                    **LedgerEventResponse(
                        event_id=e.event_id,
                        event_type=e.event_type,
                        actor=e.actor,
                        summary=e.summary,
                        details=e.details,
                        prev_event_hash=e.prev_event_hash,
                        event_hash=e.event_hash,
                        created_at=e.created_at,
                    ).model_dump(
                        mode="json", exclude={"persisted", "idempotent_replay", "chain_head"}
                    ),
                    # The exact string hashed into event_hash, for offline recomputation.
                    "created_at_canonical": canonical_timestamp(e.created_at),
                }
                for e in events
            ],
            "checkpoint": checkpoint,
            "verification": {
                "chain": LedgerChainVerifyRequest(**chain).model_dump(mode="json"),
                "certificate_signature_valid": certificate_signature_valid,
                "genome_hashes_valid": not hash_mismatches,
                "genome_hash_mismatches": hash_mismatches,
                "how_to_verify": (
                    "Recompute each event_hash as SHA-256 of the pgl-c14n JSON of {event_id, "
                    "event_type, agent_id, actor, summary, details, prev_event_hash, created_at} "
                    "using created_at_canonical as created_at; recompute each genome_hash as SHA-256 of "
                    "the pgl-c14n payload; verify certificate, checkpoint and bundle signatures "
                    "with signing_key over the pgl-c14n bytes of the signed object minus its "
                    "signature field."
                ),
            },
            "signing_key": signer.public_descriptor(),
            "retention": {
                "log_retention_days": latest.log_retention_days if latest else None,
                "statement": RETENTION_STATEMENT,
            },
            "limitations": LIMITATIONS,
        }
        bundle["bundle_signature"] = signer.sign(bundle)
        return bundle
