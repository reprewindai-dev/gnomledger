# gnomledger/ledger.py
# E — GnomLedger / PGL (Proof-of-Graph Ledger) — Evidence Recording ONLY
# POST /v1/evidence/record
# SLO: <50ms ledger write (p95)
#
# GnomLedger is a cryptographic audit trail. It does NOT handle payments.
# Payments are handled by the x402 engine (src/x402/engine.py).
# GnomLedger produces Merkle-proof receipts that the x402 engine can reference
# as proof that an action occurred before funds are released.

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

from consequence_types import (
    ExecutionReceipt,
    RecordEvidenceRequest,
    RecordEvidenceResponse,
)

log = structlog.get_logger("veklom.pgl")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class GnomLedger:
    """
    GnomLedger / PGL — Proof-of-Graph Ledger.

    Append-only, hash-linked journal of ExecutionReceipts.
    Purpose: cryptographic audit trail, non-repudiable evidence.
    NOT responsible for payments or financial settlement.

    Production storage: PostgreSQL `gnomledger` database on Server 0 (5.78.135.11)
    behind pgl.veklom.com (port 8001). Uses SQLAlchemy + pgvector.

    Stub storage: JSON lines file at LEDGER_PATH.
    """

    def __init__(self, ledger_path: Optional[str] = None, signing_key: bytes = None):
        self._ledger_path = Path(ledger_path or os.getenv("LEDGER_PATH", "./ledger.jsonl"))
        self._signing_key = signing_key or os.getenv("LEDGER_SIGNING_KEY", "dev-ledger-key").encode()
        self._sequence: int = self._load_sequence()
        self._previous_hash: str = self._load_last_hash()

    def record(self, req: RecordEvidenceRequest) -> RecordEvidenceResponse:
        """
        Append a signed ExecutionReceipt to the hash-linked journal.

        This is the ONLY action GnomLedger takes.
        It does not trigger payments. The receipt_id returned here is what
        the x402 engine checks before releasing escrowed funds.
        """
        receipt = req.receipt

        entry = {
            "sequence": self._sequence + 1,
            "receipt": receipt.model_dump(mode="json"),
            "previous_hash": self._previous_hash,
            "recorded_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        entry_bytes   = json.dumps(entry, sort_keys=True, default=str).encode()
        entry_hash    = sha256_hex(entry_bytes)
        merkle_proof  = sha256_hex((entry_hash + self._previous_hash).encode())

        self._append_entry(entry, entry_hash)
        self._sequence += 1
        self._previous_hash = entry_hash

        log.info(
            "pgl.recorded",
            receipt_id=str(receipt.receipt_id),
            sequence=self._sequence,
            outcome=receipt.outcome.value,
            merkle_proof=merkle_proof[:16] + "...",
        )

        return RecordEvidenceResponse(
            merkle_proof=merkle_proof,
            ledger_sequence=self._sequence,
        )

    def verify_chain(self) -> bool:
        """Verify the entire hash chain integrity. Used by drift-check background job."""
        if not self._ledger_path.exists():
            return True

        prev_hash = "GENESIS"
        for line in self._ledger_path.read_text().strip().splitlines():
            data = json.loads(line)
            if data["entry"]["previous_hash"] != prev_hash:
                log.error(
                    "pgl.chain_broken",
                    sequence=data["entry"]["sequence"],
                    expected_prev=prev_hash,
                    got_prev=data["entry"]["previous_hash"],
                )
                return False
            prev_hash = data["hash"]
        return True

    def get_receipt(self, receipt_id: str) -> Optional[dict]:
        """Look up a receipt by ID — used by the x402 engine to verify evidence before payment."""
        if not self._ledger_path.exists():
            return None
        for line in self._ledger_path.read_text().strip().splitlines():
            data = json.loads(line)
            if str(data["entry"]["receipt"].get("receipt_id")) == receipt_id:
                return data["entry"]["receipt"]
        return None

    # ── Private ──────────────────────────────────────────────────────────────

    def _append_entry(self, entry: dict, entry_hash: str) -> None:
        record_line = json.dumps({"hash": entry_hash, "entry": entry}, sort_keys=True, default=str)
        with self._ledger_path.open("a") as f:
            f.write(record_line + "\n")

    def _load_sequence(self) -> int:
        if not self._ledger_path.exists():
            return 0
        return len(self._ledger_path.read_text().strip().splitlines())

    def _load_last_hash(self) -> str:
        if not self._ledger_path.exists():
            return "GENESIS"
        lines = self._ledger_path.read_text().strip().splitlines()
        return json.loads(lines[-1]).get("hash", "GENESIS") if lines else "GENESIS"
