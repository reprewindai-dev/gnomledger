"""Server-generated agent handles: <OperatorInitials>-<OperatorShortId>-<runSeq>.

Agents are generic and disposable, so nobody types their names. The handle is derived from
the authenticated operator and locked server-side; a client cannot choose or spoof it.

In this ledger the operator is the authenticated account (the workspace tenant):
- OperatorInitials: initials of the account owner's full name (User.full_name, set at
  bootstrap via admin_full_name), falling back to the account name, then "OP".
- OperatorShortId: first 8 hex of SHA-256("pgl-account:<account id>"). Accounts here have
  integer ids, not UUIDs; this is a stable short id derived from the account on file.
- runSeq: 1, 2, 3, ... per account, never reused.
"""

from __future__ import annotations

import hashlib
import re

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models

_ATTEMPTS = 5


def operator_initials(db: Session, account: models.Account) -> str:
    owner_name = db.execute(
        select(models.User.full_name)
        .where(models.User.account_id == account.id, models.User.full_name.is_not(None))
        .order_by((models.User.role == "owner").desc(), models.User.id.asc())
        .limit(1)
    ).scalar_one_or_none()
    for source in (owner_name, account.name):
        words = re.findall(r"[A-Za-z0-9]+", source or "")
        initials = "".join(word[0] for word in words[:3]).upper()
        if initials:
            return initials
    return "OP"


def operator_short_id(account: models.Account) -> str:
    return hashlib.sha256(f"pgl-account:{account.id}".encode("ascii")).hexdigest()[:8]


def allocate_handle(db: Session, account: models.Account, agent_id: str) -> models.AgentHandle:
    """Reserve the operator's next handle for agent_id. Must run before the registration's
    other writes: a lost race rolls the session back and retries with the next number."""
    prefix = f"{operator_initials(db, account)}-{operator_short_id(account)}"
    for _ in range(_ATTEMPTS):
        last = db.execute(
            select(func.max(models.AgentHandle.seq)).where(
                models.AgentHandle.account_id == account.id
            )
        ).scalar_one()
        seq = (last or 0) + 1
        row = models.AgentHandle(
            account_id=account.id, seq=seq, handle=f"{prefix}-{seq}", agent_id=agent_id
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            continue
        return row
    raise RuntimeError("Could not allocate an agent handle; retry the registration")


def handle_for(db: Session, agent_id: str) -> str | None:
    return db.execute(
        select(models.AgentHandle.handle).where(models.AgentHandle.agent_id == agent_id)
    ).scalar_one_or_none()
