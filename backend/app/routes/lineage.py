from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db, require_role
from ..schemas import AgentResponse, LineageForkRequest, LineageTreeNode
from ..services.lineage_service import LineageService

router = APIRouter(prefix="/lineage")


@router.post("/fork", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def fork_agent(
    payload: LineageForkRequest,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("operator", "admin", "owner")),
) -> AgentResponse:
    service = LineageService(db)
    try:
        return service.fork_agent(
            account_id=ctx.account_id,
            source_agent_id=payload.source_agent_id,
            new_name=payload.new_name,
            creator=payload.creator,
            jurisdiction=payload.jurisdiction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/tree/{agent_id}", response_model=LineageTreeNode)
def get_lineage_tree(
    agent_id: str,
    db: Session = Depends(get_db),
    ctx=Depends(require_role("viewer", "operator", "admin", "owner")),
) -> LineageTreeNode:
    service = LineageService(db)
    try:
        return service.get_tree(ctx.account_id, agent_id)
    except ValueError as exc:
        if "quota" in str(exc).lower():
            status_code = status.HTTP_402_PAYMENT_REQUIRED
        elif "unknown" in str(exc).lower():
            status_code = status.HTTP_404_NOT_FOUND
        else:
            status_code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
