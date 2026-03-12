from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas import AgentResponse, LineageTreeNode
from ..services.lineage_service import LineageService

router = APIRouter()


@router.post("/fork", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def fork_agent(
    source_agent_id: str,
    new_name: str,
    creator: str,
    jurisdiction: str,
    db: Session = Depends(get_db),
) -> AgentResponse:
    service = LineageService(db)
    try:
        return service.fork_agent(source_agent_id, new_name, creator, jurisdiction)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tree/{agent_id}", response_model=LineageTreeNode)
def get_lineage_tree(agent_id: str, db: Session = Depends(get_db)) -> LineageTreeNode:
    service = LineageService(db)
    try:
        return service.get_tree(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
