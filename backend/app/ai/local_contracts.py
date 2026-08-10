"""Validated contracts for zero-credit operational queries."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


QueryOperation = Literal[
    "find", "count", "detail", "reverse_lookup", "status", "relationship",
    "aggregate", "rank", "compare", "trend", "exceptions", "attention",
    "history", "group", "buyers",
]


class DateWindow(BaseModel):
    start: datetime
    end: datetime
    label: str


class ResolvedEntity(BaseModel):
    kind: str
    id: str
    display_name: str
    confidence: float = Field(ge=0, le=1)
    profile_ref: dict | None = None


class BusinessQueryV1(BaseModel):
    schema_version: Literal[1] = 1
    engine: Literal["local_v1"] = "local_v1"
    intent: str
    domain: str
    operation: QueryOperation
    subject: str
    metric: str | None = None
    language: Literal["en", "ta", "tanglish"] = "en"
    query_text: str | None = None
    status: str | None = None
    min_amount_paise: int | None = Field(default=None, ge=0)
    max_amount_paise: int | None = Field(default=None, ge=0)
    location_id: str | None = None
    date_range: DateWindow | None = None
    comparison_range: DateWindow | None = None
    entities: list[ResolvedEntity] = Field(default_factory=list)
    group_by: str | None = None
    granularity: Literal["day", "week", "month"] = "day"
    sort: str | None = None
    direction: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=5, ge=1, le=100)
    confidence: float = Field(ge=0, le=1)


class QueryClarification(BaseModel):
    reason: Literal["ambiguous_entity", "ambiguous_intent"]
    message: str
    candidates: list[dict] = Field(default_factory=list)


class IntentMatch(BaseModel):
    outcome: Literal["local", "clarify", "fallback"]
    confidence: float = Field(ge=0, le=1)
    query: BusinessQueryV1 | None = None
    clarification: QueryClarification | None = None
    reason: str | None = None


class QueryExecutionResult(BaseModel):
    summary: str
    result: dict
    query: BusinessQueryV1
