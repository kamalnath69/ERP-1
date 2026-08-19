"""Unversioned contracts for the governed Edvatiq assistant."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PresentationFormat = Literal[
    "text", "number", "decimal", "percent", "currency_paise",
    "date", "datetime", "status", "relation", "tags", "collection",
    "boolean",
]
PresentationRole = Literal[
    "title", "subtitle", "badge", "metric", "detail", "collection",
]
PresentationLayout = Literal[
    "profile", "cards", "ranking", "comparison", "metrics", "chart",
    "sources", "notice", "clarification", "action", "processing",
]


class AssistantOutcome(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    CLARIFICATION = "clarification"
    PROCESSING = "processing"
    EMPTY = "empty"
    NOT_FOUND = "not_found"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    ACCESS_LIMITED = "access_limited"
    ENTITLEMENT_REQUIRED = "entitlement_required"
    QUOTA_EXHAUSTED = "quota_exhausted"
    CONFIGURATION_REQUIRED = "configuration_required"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"


class QueryGoal(StrEnum):
    PROFILE = "profile"
    LIST = "list"
    COMPARE = "compare"
    RANK = "rank"
    AGGREGATE = "aggregate"
    TREND = "trend"
    CORRELATION = "correlation"
    ELIGIBILITY = "eligibility"
    MATCH = "match"
    ANALYZE = "analyze"
    ACTION = "action"
    GENERAL = "general"
    CLARIFY = "clarify"


class FilterOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    IS_NULL = "is_null"


class EntityRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=60)
    id: str | None = Field(default=None, max_length=100)
    label: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def has_identity(self):
        if not self.id and not self.label:
            raise ValueError("An entity reference needs an id or label")
        return self


class QueryFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=100)
    operator: FilterOperator
    value: Any = None


class QuerySort(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=100)
    direction: Literal["asc", "desc"] = "asc"


class TimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str | None = Field(default=None, max_length=40)
    end: str | None = Field(default=None, max_length=40)
    preset: Literal[
        "current", "previous", "last_30_days", "last_90_days",
        "this_academic_year", "previous_academic_year", "all",
    ] | None = None


class SemanticQuery(BaseModel):
    """Strict intermediate representation with no executable expressions."""

    model_config = ConfigDict(extra="forbid")

    goal: QueryGoal
    entity: str = Field(min_length=1, max_length=60)
    fields: list[str] = Field(default_factory=list, max_length=80)
    metrics: list[str] = Field(default_factory=list, max_length=30)
    filters: list[QueryFilter] = Field(default_factory=list, max_length=40)
    group_by: list[str] = Field(default_factory=list, max_length=5)
    sort: list[QuerySort] = Field(default_factory=list, max_length=5)
    entities: list[EntityRef] = Field(default_factory=list, max_length=20)
    time_window: TimeWindow | None = None
    limit: int = Field(default=25, ge=1, le=100)
    qualitative_definition: str | None = Field(default=None, max_length=80)
    requested_analysis: str | None = Field(default=None, max_length=120)


class PageContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: str | None = Field(default=None, max_length=500)
    entity: EntityRef | None = None
    selected_entities: list[EntityRef] = Field(default_factory=list, max_length=20)
    location_id: str | None = Field(default=None, max_length=100)
    department_id: str | None = Field(default=None, max_length=100)
    program_id: str | None = Field(default=None, max_length=100)
    cohort_ids: list[str] = Field(default_factory=list, max_length=50)
    graduation_year: int | None = Field(default=None, ge=2000, le=2200)


class AssistantInteraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["select_entity"]
    clarification_id: str = Field(min_length=1, max_length=100)
    entity: EntityRef


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str | None = Field(default=None, max_length=100)
    message: str | None = Field(default=None, min_length=1, max_length=5000)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=160)
    context: PageContext | None = None
    interaction: AssistantInteraction | None = None

    @model_validator(mode="after")
    def message_or_interaction(self):
        if bool(self.message) == bool(self.interaction):
            raise ValueError("Provide either a message or an interaction")
        return self


class ResolvedScope(BaseModel):
    organization_id: str
    user_id: str
    industry: str
    owner: bool = False
    policy_version: int = 0
    permission_codes: list[str] = Field(default_factory=list)
    domain_levels: dict[str, str] = Field(default_factory=dict)
    scope_labels: dict[str, Any] = Field(default_factory=dict)


class Observation(BaseModel):
    id: str
    kind: str
    entity: str
    facts: dict[str, Any] = Field(default_factory=dict)
    source: str
    source_timestamp: datetime | None = None
    sample_size: int | None = None
    population_size: int | None = None
    coverage_percent: float | None = None
    definitions: dict[str, str] = Field(default_factory=dict)
    authorized_scope: str


class ArtifactSecurity(BaseModel):
    permissions: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    entity_ids: list[str] = Field(default_factory=list, max_length=500)
    entity_refs: list[EntityRef] = Field(default_factory=list, max_length=500)


class PresentationField(BaseModel):
    """One catalog-approved value that may be rendered to a user."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=160)
    format: PresentationFormat = "text"
    group: str = Field(default="Details", min_length=1, max_length=80)
    role: PresentationRole = "detail"
    priority: int = Field(default=100, ge=0, le=1000)


class ArtifactPresentation(BaseModel):
    """Typed, display-only instructions derived from the semantic catalog."""

    model_config = ConfigDict(extra="forbid")

    layout: PresentationLayout
    entity: str | None = Field(default=None, max_length=60)
    fields: list[PresentationField] = Field(default_factory=list, max_length=100)
    preview_limit: int | None = Field(default=None, ge=1, le=12)


class Artifact(BaseModel):
    id: str
    type: Literal[
        "profile", "records", "ranking", "comparison", "metric",
        "chart", "sources", "notice", "clarification", "action",
        "processing",
    ]
    title: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    presentation: ArtifactPresentation | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    security: ArtifactSecurity = Field(default_factory=ArtifactSecurity)


class Suggestion(BaseModel):
    id: str
    label: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=500)
    entity_refs: list[EntityRef] = Field(default_factory=list, max_length=5)
    security: ArtifactSecurity = Field(default_factory=ArtifactSecurity)


class AssistantResponse(BaseModel):
    outcome: AssistantOutcome
    answer: str
    artifacts: list[Artifact] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    scope: ResolvedScope | None = None
    result_session_id: str | None = None
    trace_id: str | None = None


class ConversationReferent(BaseModel):
    ref: EntityRef
    source: Literal["page", "selection", "message", "result"]
    turn_id: str | None = None
    named: bool = False


class ConversationState(BaseModel):
    referents: list[ConversationReferent] = Field(default_factory=list, max_length=20)
    pending_clarification: dict[str, Any] | None = None
    last_query: SemanticQuery | None = None
    policy_version: int = 0
