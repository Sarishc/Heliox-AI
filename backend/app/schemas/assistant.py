"""Schemas for assistant queries."""

from typing import Any, Dict

from pydantic import BaseModel, Field


class AssistantQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


class AssistantToolTrace(BaseModel):
    tool: str
    params: Dict[str, Any]
    status: str = Field(default="ok")
    duration_ms: float | None = None
    row_count: int | None = None
    query_count: int | None = None
    cache_hit: bool | None = None


class AssistantQueryResponse(BaseModel):
    tool_used: str
    answer: str
    data: Dict[str, Any]
    fallback: bool
    tool_trace: AssistantToolTrace
