"""Assistant query endpoint."""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import get_team_api_key_optional
from app.core.tenant import get_effective_team_id
from app.core.usage_tracking import record_api_usage
from app.models.team_api_key import TeamAPIKey
from app.schemas.assistant import AssistantQueryRequest, AssistantQueryResponse
from app.services.assistant import AssistantQueryService

router = APIRouter()


@router.post(
    "/query",
    response_model=AssistantQueryResponse,
    summary="Query Heliox analytics with natural language"
)
def query_assistant(
    payload: AssistantQueryRequest,
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> Any:
    team_id = get_effective_team_id(team_api_key)
    service = AssistantQueryService(db)
    try:
        response = service.handle(team_id=team_id, question=payload.question)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    record_api_usage(db, team_id=team_id, endpoint="assistant_query")
    return response
