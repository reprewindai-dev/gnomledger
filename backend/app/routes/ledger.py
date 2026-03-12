from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas import LedgerEventCreate, LedgerEventResponse
from ..services.ledger_service import LedgerService

router = APIRouter()


@router.post("/events", response_model=LedgerEventResponse, status_code=status.HTTP_201_CREATED)
def create_ledger_event(payload: LedgerEventCreate, db: Session = Depends(get_db)) -> LedgerEventResponse:
    service = LedgerService(db)
    try:
        return service.log_event(payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/agents/{agent_id}", response_model=list[LedgerEventResponse])
def get_agent_history(agent_id: str, db: Session = Depends(get_db)) -> list[LedgerEventResponse]:
    service = LedgerService(db)
    try:
        return service.get_agent_history(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
