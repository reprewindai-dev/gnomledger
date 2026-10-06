from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..dependencies import get_db, require_role
from .. import models
from ..schemas import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyListItem,
    BootstrapRequest,
    PGLRequestContext,
)
from ..services.key_service import ApiKeyService

router = APIRouter()
settings = get_settings()


def _authorize_account(ctx: PGLRequestContext, account_id: int) -> None:
    """Admins administer keys for their own account only; owners may administer any.

    A foreign account answers 404 exactly like a nonexistent one so it is not enumerable.
    """
    if ctx.role != "owner" and ctx.account_id != account_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown account_id")


@router.post("/bootstrap", response_model=ApiKeyCreateResponse)
def bootstrap(
    payload: BootstrapRequest,
    db: Session = Depends(get_db),
):
    if payload.bootstrap_token != settings.bootstrap_admin_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bootstrap token")

    existing = db.execute(select(models.Account)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bootstrap already completed")

    account = models.Account(name=payload.account_name, tier=payload.account_tier)
    db.add(account)
    db.flush()
    admin_user = models.User(account_id=account.id, email=payload.admin_name, role="owner")
    db.add(admin_user)
    db.flush()

    service = ApiKeyService(db)
    try:
        raw_key, key = service.issue_api_key(
            account_id=account.id,
            payload=ApiKeyCreateRequest(
                name="bootstrap-admin",
                role="owner",
                scopes=["*"],
                account_id=account.id,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ApiKeyCreateResponse(
        api_key=raw_key,
        api_key_prefix=key.key_prefix,
        account_id=account.id,
        role=key.role,
        scopes=key.scopes,
    )


@router.post("/accounts/{account_id}/keys", response_model=ApiKeyCreateResponse)
def create_api_key(
    account_id: int,
    payload: ApiKeyCreateRequest,
    db: Session = Depends(get_db),
    ctx: PGLRequestContext = Depends(require_role("admin", "owner")),
):
    _authorize_account(ctx, account_id)
    if payload.account_id is not None and payload.account_id != account_id:
        # The body must not redirect the key to an account other than the authorized one.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="account_id in body must match the account in the path",
        )
    account = db.execute(select(models.Account).where(models.Account.id == account_id)).scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown account_id")
    service = ApiKeyService(db)
    try:
        raw_key, key = service.issue_api_key(
            account_id=account_id, payload=payload, issuer_role=ctx.role
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ApiKeyCreateResponse(
        api_key=raw_key,
        api_key_prefix=key.key_prefix,
        account_id=account_id,
        role=key.role,
        scopes=key.scopes,
    )


@router.get("/accounts/{account_id}/keys", response_model=list[ApiKeyListItem])
def list_api_keys(
    account_id: int,
    db: Session = Depends(get_db),
    ctx: PGLRequestContext = Depends(require_role("admin", "owner")),
):
    _authorize_account(ctx, account_id)
    account = db.execute(select(models.Account).where(models.Account.id == account_id)).scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown account_id")
    service = ApiKeyService(db)
    keys = service.list_api_keys(account_id=account_id)
    return [
        ApiKeyListItem(
            id=key.id,
            account_id=key.account_id,
            name=key.name,
            key_prefix=key.key_prefix,
            role=key.role,
            scopes=key.scopes,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            revoked_at=key.revoked_at,
            expires_at=key.expires_at,
        )
        for key in keys
    ]


@router.delete("/accounts/{account_id}/keys/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    account_id: int,
    api_key_id: int,
    db: Session = Depends(get_db),
    ctx: PGLRequestContext = Depends(require_role("admin", "owner")),
):
    _authorize_account(ctx, account_id)
    service = ApiKeyService(db)
    try:
        service.revoke_api_key(account_id=account_id, api_key_id=api_key_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return None
