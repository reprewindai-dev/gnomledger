from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas import AgentCreateRequest, AgentResponse, GenomePayload, GenomeUpdateRequest
from ..services.certificate_service import CertificateService
from ..services.genome_service import GenomeService

router = APIRouter()


@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreateRequest, db: Session = Depends(get_db)) -> AgentResponse:
    service = CertificateService(db)
    try:
        return service.register_agent(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{agent_id}/genome", response_model=GenomePayload)
def update_genome(agent_id: str, payload: GenomeUpdateRequest, db: Session = Depends(get_db)) -> GenomePayload:
    service = GenomeService(db)
    try:
        return service.update_genome(agent_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
