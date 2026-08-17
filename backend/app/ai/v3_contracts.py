"""Internal, versioned contracts for the V3 AI execution pipeline."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


LanguageCode = Literal["en", "ta", "tanglish"]
PlannerKind = Literal["conversation", "local", "deterministic", "model", "cache"]
RiskLevel = Literal["low", "medium", "high"]


class PlanStepV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40)
    tool: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, max_length=8)
    read_only: bool = True


class AIQueryPlanV2(BaseModel):
    """A validated plan produced locally or by the capability-scoped planner."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    domain: str = Field(default="business", min_length=1, max_length=60)
    operation: str = Field(default="answer", min_length=1, max_length=80)
    language: LanguageCode = "en"
    unresolved_references: list[str] = Field(default_factory=list, max_length=8)
    validated_scope: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    date_window: dict[str, Any] | None = None
    metrics: list[str] = Field(default_factory=list, max_length=12)
    sorting: list[dict[str, Any]] = Field(default_factory=list, max_length=8)
    presentation: Literal["text", "cards", "table", "chart", "auto"] = "auto"
    risk: RiskLevel = "low"
    synthesis_required: bool = True
    requires_exact_count: bool = False
    planner_kind: PlannerKind = "model"
    confidence: float = Field(default=0.0, ge=0, le=1)
    clarification: str | None = Field(default=None, max_length=500)
    direct_answer: str | None = Field(default=None, max_length=5000)
    local_query: dict[str, Any] | None = None
    steps: list[PlanStepV2] = Field(default_factory=list, max_length=8)

    @field_validator("unresolved_references")
    @classmethod
    def normalize_references(cls, value: list[str]) -> list[str]:
        return [" ".join(item.split()) for item in value if item and item.strip()]


class EvidenceFactV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^E\d+$")
    source: str = Field(min_length=1, max_length=100)
    source_id: str | None = Field(default=None, max_length=160)
    fact: str = Field(min_length=1, max_length=1600)
    freshness: str | None = Field(default=None, max_length=80)
    citation_index: int | None = Field(default=None, ge=0)


class EvidenceBundleV1(BaseModel):
    """Compact model input; UI payloads and private tool internals are excluded."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    facts: list[EvidenceFactV1] = Field(default_factory=list, max_length=40)
    missing_evidence: list[str] = Field(default_factory=list, max_length=12)
    warnings: list[str] = Field(default_factory=list, max_length=12)
    citations: list[dict[str, Any]] = Field(default_factory=list, max_length=12)


class GroundedClaimV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1200)
    evidence_ids: list[str] = Field(default_factory=list, max_length=12)


class GroundedAnswerV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    content: str = Field(min_length=1, max_length=12000)
    claims: list[GroundedClaimV2] = Field(default_factory=list, max_length=40)
    used_evidence_ids: list[str] = Field(default_factory=list, max_length=40)


class VerificationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["passed", "repaired", "deterministic_fallback", "not_required"]
    unsupported_claims: list[str] = Field(default_factory=list, max_length=20)
    invalid_evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    high_risk: bool = False


class StageTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    durations_ms: dict[str, int] = Field(default_factory=dict)
    planner_kind: str = "unknown"
    planner_confidence: float = Field(default=0, ge=0, le=1)
    cache_status: str = "miss"
    model_rounds: int = Field(default=0, ge=0, le=3)
    first_event_latency_ms: int | None = Field(default=None, ge=0)
    verification_outcome: str = "not_required"
    fallback_used: bool = False

