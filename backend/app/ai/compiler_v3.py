"""Single conservative compiler for local V3 execution decisions."""
from dataclasses import dataclass
import re

from sqlalchemy.orm import Session

from app.ai.fast_queries import deterministic_query_plan
from app.ai.local_contracts import IntentMatch
from app.ai.local_intent import interpret_business_query, normalize_language
from app.ai.orchestrator import fast_conversation_reply
from app.ai.personalization import AssistantPreferences
from app.ai.v3_cache import PLAN_CACHE
from app.ai.v3_contracts import AIQueryPlanV2, PlanStepV2
from app.models import User


@dataclass
class CompilationResult:
    plan: AIQueryPlanV2
    local_match: IntentMatch | None = None
    deterministic_plan: dict | None = None
    fast_reply: dict | None = None
    cache_status: str = "miss"


def requests_exact_count(message: str) -> bool:
    normalized = " ".join(message.casefold().split())
    return any(re.search(pattern, normalized, flags=re.UNICODE) for pattern in (
        r"(?<!\w)how many(?!\w)",
        r"(?<!\w)count(?!\w)",
        r"(?<!\w)number of(?!\w)",
        r"(?<!\w)evlo(?!\w)",
        r"(?<!\w)எத்தனை(?!\w)",
    ))


def _explicit_knowledge_query(message: str, context: dict | None) -> bool:
    text = " ".join(message.casefold().split())
    if (context or {}).get("kind") == "document":
        return len(text.split()) >= 2
    patterns = (
        r"^(?:what|summarize|explain|show|find)\b.{0,80}\b(?:policy|document|manual|sop|pdf)\b",
        r"^(?:according to|in)\s+(?:the\s+)?(?:policy|document|manual|sop)\b",
    )
    return 3 <= len(text.split()) <= 40 and any(re.search(pattern, text) for pattern in patterns)


def compile_turn(
    db: Session,
    user: User,
    message: str,
    *,
    industry: str,
    location_id: str | None,
    context_state: dict | None,
    explicit_context: dict | None,
    preferences: AssistantPreferences,
) -> CompilationResult:
    language = normalize_language(message)[1]
    reply = fast_conversation_reply(message, preferences)
    if reply:
        return CompilationResult(
            plan=AIQueryPlanV2(
                domain="conversation", operation=reply["intent"], language=language,
                synthesis_required=False, planner_kind="conversation", confidence=1,
                direct_answer=reply["content"],
            ),
            fast_reply=reply,
        )

    if industry != "college":
        local_match = interpret_business_query(db, user, message, location_id, context_state)
        if local_match.outcome in {"local", "clarify"}:
            query = local_match.query.model_dump(mode="json") if local_match.query else None
            clarification = local_match.clarification.message if local_match.clarification else None
            return CompilationResult(
                plan=AIQueryPlanV2(
                    domain="business", operation="clarify" if clarification else "structured_read",
                    language=language, synthesis_required=False, planner_kind="local",
                    confidence=local_match.confidence, clarification=clarification, local_query=query,
                    risk="low", requires_exact_count=requests_exact_count(message),
                ),
                local_match=local_match,
            )

    context_free = not location_id and not context_state and not explicit_context
    cache_key = (industry, re.sub(r"\s+", " ", message.casefold()).strip())
    cached = PLAN_CACHE.get(cache_key) if context_free else None
    candidate = cached if cached is not None else deterministic_query_plan(message, location_id, context_state)
    if context_free and cached is None and candidate:
        PLAN_CACHE.set(cache_key, candidate)
    if candidate:
        arguments = candidate.get("arguments") or {}
        if industry != "college" or (
            candidate.get("tool") == "business_records"
            and arguments.get("subject") == "students"
            and set(arguments).issubset({"subject", "location_id", "status"})
            and not (explicit_context or {}).get("kind") == "college_scope"
            and not (context_state or {}).get("college_scope")
        ):
            return CompilationResult(
                plan=AIQueryPlanV2(
                    domain="college" if industry == "college" else "business",
                    operation="structured_read", language=language, synthesis_required=False,
                    planner_kind="cache" if cached is not None else "deterministic",
                    confidence=0.99, requires_exact_count=requests_exact_count(message),
                    steps=[PlanStepV2(id="read-1", tool=candidate["tool"], arguments=arguments)],
                ),
                deterministic_plan=candidate,
                cache_status="hit" if cached is not None else "miss",
            )

    if _explicit_knowledge_query(message, explicit_context):
        document_id = (explicit_context or {}).get("id") if (explicit_context or {}).get("kind") == "document" else None
        return CompilationResult(
            plan=AIQueryPlanV2(
                domain="knowledge", operation="document_answer", language=language,
                planner_kind="local", confidence=0.97, synthesis_required=True,
                steps=[PlanStepV2(
                    id="knowledge-1", tool="search_knowledge",
                    arguments={"query": message, "document_id": document_id},
                )],
            ),
        )

    return CompilationResult(plan=AIQueryPlanV2(
        domain="college" if industry == "college" else "business",
        operation="plan", language=language, planner_kind="model", confidence=0,
        synthesis_required=True,
    ))
