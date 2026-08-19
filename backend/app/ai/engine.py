"""The single unversioned Edvatiq assistant engine."""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.ai.access import AccessViolation, resolve_access_envelope
from app.ai.catalog import catalog_for
from app.ai.compiler import CompileResult, compile_query
from app.ai.contracts import (
    Artifact, AssistantOutcome, AssistantRequest, AssistantResponse,
    ConversationReferent, ConversationState, EntityRef, QueryGoal,
    SemanticQuery, Suggestion,
)
from app.ai.definitions import semantic_definitions
from app.ai.domains.common import identifier, security
from app.ai.execution import execute_semantic_query
from app.ai.personalization import (
    load_assistant_preferences, model_style_instruction,
    style_deterministic_summary,
)
from app.ai.presentation import redact_internal_identifiers, sanitize_display_data
from app.ai.provider import ProviderResponse, provider as configured_provider
from app.core.config import settings
from app.models import User


@dataclass
class EngineUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    provider_requests: int = 0

    def add(self, response: ProviderResponse | None) -> None:
        if not response:
            return
        self.input_tokens += response.input_tokens
        self.cached_input_tokens += response.cached_input_tokens
        self.output_tokens += response.output_tokens
        self.provider_requests += response.provider_requests


@dataclass
class EngineResult:
    response: AssistantResponse
    state: ConversationState
    query: SemanticQuery | None = None
    usage: EngineUsage = field(default_factory=EngineUsage)
    stage_durations_ms: dict[str, int] = field(default_factory=dict)
    deterministic_compile: bool = False


STRICT_ANSWER_TOOL = {
    "type": "function",
    "name": "submit_answer",
    "description": "Submit a concise conversational answer grounded only in the supplied observations.",
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "sections": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "text": {"type": "string"},
                        "evidence_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    },
                    "required": ["text", "evidence_ids"],
                },
            },
        },
        "required": ["sections"],
    },
}


ANSWER_SYSTEM = """You are Edvatiq, a natural, human-first ERP assistant.
Lead with the direct answer, then explain only the highlights relevant to the request. Prefer short, flowing paragraphs over field dumps, semicolon chains, or robotic templates. Use only supplied observations. Every section must cite one or more valid observation IDs.
Do not infer missing values, expand the authorized population, claim causation, predict employment probability, or mention hidden implementation details.
Never expose database IDs, UUIDs, security labels, routing IDs, or semantic references. Do not mention missing fields unless the absence matters to the user's request; combine related missing evidence into one natural sentence.
Keep scope and evidence limitations explicit. Do not repeat a raw record dump because the cards already show supporting details."""


GENERAL_SYSTEM = """You are Edvatiq, a helpful ERP assistant. Answer the safe general question conversationally.
Do not claim to have searched the web or organizational documents. Do not invent organization-specific facts.
If the user asks for organizational data, explain that an approved semantic query and their current access are required."""

_CONFIGURED_PROVIDER = object()


def _response_function_arguments(response: ProviderResponse, name: str) -> dict[str, Any]:
    calls = []
    for item in response.output:
        payload = item.model_dump(mode="json", exclude_none=True) if hasattr(item, "model_dump") else item
        if isinstance(payload, dict) and payload.get("type") == "function_call" and payload.get("name") == name:
            calls.append(payload)
    if len(calls) != 1:
        raise ValueError(f"Expected one {name} call")
    raw = calls[0].get("arguments")
    return json.loads(raw) if isinstance(raw, str) else dict(raw or {})


def _clarification(query: SemanticQuery, scope) -> AssistantResponse:
    reason = query.requested_analysis
    if reason == "ambiguous_best":
        options = [
            {"label": "Highest CGPA", "prompt": "Who are the top 10 students by CGPA?"},
            {"label": "Placement readiness", "prompt": "Who are the top 10 students by placement readiness?"},
            {"label": "Best attendance", "prompt": "Who are the top 10 students by attendance?"},
        ]
        answer = "'Best' can mean different things. Choose CGPA, placement readiness, attendance, or tell me another approved measure."
    elif reason == "missing_company_referent":
        options = []
        answer = "Which company or placement drive should I use? Name it or open its profile first."
    elif reason == "undefined_student_profile_thresholds":
        options = [
            {"label": "Multiple offers", "prompt": "Show students with CGPA between 6 and 8 who received multiple offers."},
            {"label": "Currently placed", "prompt": "Show placed students with CGPA between 6 and 8."},
        ]
        answer = "What CGPA range should count as average, and should strong placement performance mean being placed, receiving offers, or another governed measure?"
    elif reason == "high_package_threshold_required":
        options = [
            {"label": "INR 10 LPA", "prompt": "Which unplaced students are eligible for packages at least INR 10 LPA?"},
            {"label": "INR 15 LPA", "prompt": "Which unplaced students are eligible for packages at least INR 15 LPA?"},
        ]
        answer = "What package threshold should count as high-package?"
    else:
        options = []
        answer = "I need an explicit student selection to continue. Name the student or open their profile first."
    return AssistantResponse(
        outcome=AssistantOutcome.CLARIFICATION, answer=answer,
        artifacts=[Artifact(
            id=identifier("artifact"), type="clarification", title="Clarify the request",
            data={"reason": reason, "options": options},
            security=security(permissions=("ai.use",)),
        )],
        suggestions=[Suggestion(
            id=identifier("suggestion"), label=item["label"], prompt=item["prompt"],
        ) for item in options], scope=scope,
    )


def _deterministic_general(query: SemanticQuery, scope, industry: str) -> AssistantResponse | None:
    if query.requested_analysis in {"greeting", "greeting_tanglish", "greeting_tamil"}:
        lead = {
            "greeting": "Hello.",
            "greeting_tanglish": "Vanakkam.",
            "greeting_tamil": "Vanakkam.",
        }[query.requested_analysis]
        return AssistantResponse(
            outcome=AssistantOutcome.SUCCESS,
            answer=f"{lead} I can answer questions about the ERP data you're authorized to access, compare records, explain trends, and prepare actions for confirmation.",
            suggestions=[
                Suggestion(id=identifier("suggestion"), label="What needs attention?", prompt="What needs attention today?"),
                Suggestion(id=identifier("suggestion"), label="Show capabilities", prompt="What can you help me with?"),
            ], scope=scope,
        )
    if query.requested_analysis == "capabilities":
        college = industry == "college"
        answer = (
            "I can explain student profiles, academics, attendance, readiness, skills, placements, eligibility, rankings, comparisons, trends, and evidence-backed associations within your access."
            if college else
            "I can explain authorized clients, appointments, sales, operations, comparisons, trends, and prepare ERP actions for your confirmation."
        )
        return AssistantResponse(outcome=AssistantOutcome.SUCCESS, answer=answer, scope=scope)
    return None


async def _general_answer(
    message: str, model: str, provider, scope, style_instruction: str,
) -> tuple[AssistantResponse, ProviderResponse | None]:
    if provider is None:
        return AssistantResponse(
            outcome=AssistantOutcome.UNAVAILABLE,
            answer="I can answer ERP questions from approved data, but the conversational model is not configured for this general question.",
            scope=scope,
        ), None
    response = await provider.respond(
        model=model,
        inputs=[
            {"role": "system", "content": [{"type": "input_text", "text": f"{GENERAL_SYSTEM}\n\n{style_instruction}"}]},
            {"role": "user", "content": [{"type": "input_text", "text": message}]},
        ],
        tools=[], parallel_tool_calls=False, max_output_tokens=500,
    )
    text = redact_internal_identifiers((response.text or "").strip())
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS if text else AssistantOutcome.UNAVAILABLE,
        answer=text or "I couldn't produce a reliable answer just now.", scope=scope,
    ), response


async def _synthesize(
    *, message: str, query: SemanticQuery, response: AssistantResponse,
    model: str, provider, style_instruction: str,
) -> tuple[AssistantResponse, ProviderResponse | None]:
    if provider is None or not response.observations or response.outcome not in {
        AssistantOutcome.SUCCESS, AssistantOutcome.PARTIAL,
    }:
        return response, None
    observation_ids = {item.id for item in response.observations}
    payload = {
        "request": message,
        "semantic_query": sanitize_display_data(
            query.model_dump(mode="json"), preserve_controls=False,
        ),
        "observations": [item.model_dump(mode="json") for item in response.observations],
        "draft_answer": response.answer,
        "outcome": response.outcome.value,
    }
    result = await provider.respond(
        model=model,
        inputs=[
            {"role": "system", "content": [{"type": "input_text", "text": f"{ANSWER_SYSTEM}\n\n{style_instruction}"}]},
            {"role": "user", "content": [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=True)}]},
        ],
        tools=[STRICT_ANSWER_TOOL],
        tool_choice={"type": "function", "name": "submit_answer"},
        parallel_tool_calls=False,
        max_output_tokens=700,
    )
    arguments = _response_function_arguments(result, "submit_answer")
    sections = arguments.get("sections") or []
    if not sections or any(
        not set(section.get("evidence_ids") or []).issubset(observation_ids)
        or not section.get("evidence_ids")
        for section in sections
    ):
        raise ValueError("Answer contained an ungrounded section")
    answer = redact_internal_identifiers("\n\n".join(
        str(section.get("text") or "").strip()
        for section in sections if str(section.get("text") or "").strip()
    ))
    if not answer:
        raise ValueError("Answer was empty")
    return response.model_copy(update={"answer": answer}), result


def _load_state(value: dict | None) -> ConversationState:
    try:
        return ConversationState.model_validate(value or {})
    except ValueError:
        return ConversationState()


def _resume_selection(request: AssistantRequest, state: ConversationState) -> tuple[SemanticQuery, str]:
    interaction = request.interaction
    pending = state.pending_clarification or {}
    if not interaction or interaction.clarification_id != pending.get("id"):
        raise ValueError("This clarification is no longer active")
    allowed = set(pending.get("entity_ids") or [])
    if not interaction.entity.id or interaction.entity.id not in allowed:
        raise ValueError("The selected entity is not part of this clarification")
    query = SemanticQuery.model_validate(pending["query"])
    unresolved = list(query.entities)
    if unresolved:
        unresolved[0] = interaction.entity
    else:
        unresolved = [interaction.entity]
    return query.model_copy(update={"entities": unresolved}), str(pending.get("message") or "Continue the original request")


def _update_state(
    state: ConversationState,
    request: AssistantRequest,
    query: SemanticQuery,
    response: AssistantResponse,
    policy_version: int,
) -> ConversationState:
    referents = list(state.referents)
    if request.context:
        page_refs = [*request.context.selected_entities]
        if request.context.entity:
            page_refs.append(request.context.entity)
        for ref in page_refs:
            referents.append(ConversationReferent(ref=ref, source="page", named=False))
    if request.interaction:
        referents.append(ConversationReferent(ref=request.interaction.entity, source="selection", named=True))
    for artifact in response.artifacts:
        if artifact.type == "profile":
            reference = next(
                (item for item in artifact.security.entity_refs if item.kind == query.entity),
                None,
            )
            if reference is None and artifact.security.entity_ids:
                reference = EntityRef(
                    kind=query.entity,
                    id=str(artifact.security.entity_ids[0]),
                    label=artifact.data.get("name") or artifact.title,
                )
            if reference is None:
                continue
            referents.append(ConversationReferent(
                ref=reference.model_copy(update={
                    "label": reference.label or artifact.data.get("name") or artifact.title,
                }),
                source="result", named=True,
            ))
    deduped = []
    seen = set()
    for item in reversed(referents):
        key = (item.ref.kind, item.ref.id, item.ref.label)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    referents = list(reversed(deduped[:20]))

    pending = None
    clarification = next((item for item in response.artifacts if item.type == "clarification" and item.data.get("clarification_id")), None)
    if clarification:
        options = clarification.data.get("options") or []
        pending = {
            "id": clarification.data["clarification_id"],
            "query": query.model_dump(mode="json"),
            "message": request.message,
            "entity_ids": [
                (item.get("entity") or {}).get("id") for item in options
                if (item.get("entity") or {}).get("id")
            ],
        }
    return ConversationState(
        referents=referents,
        pending_clarification=pending,
        last_query=query,
        policy_version=policy_version,
    )


async def run_assistant_turn(
    *,
    request: AssistantRequest,
    user: User,
    db: Session,
    conversation_state: dict | None = None,
    provider_override=_CONFIGURED_PROVIDER,
) -> EngineResult:
    started = time.perf_counter()
    usage = EngineUsage()
    stages: dict[str, int] = {}
    state = _load_state(conversation_state)
    try:
        envelope = resolve_access_envelope(db, user)
    except AccessViolation as exc:
        return EngineResult(
            response=AssistantResponse(outcome=exc.outcome, answer=exc.message),
            state=state,
        )
    catalog = catalog_for(envelope.industry)
    definitions = semantic_definitions(db, envelope.organization_id)
    preferences = load_assistant_preferences(db, user)
    style_instruction = model_style_instruction(preferences, user)
    provider = configured_provider() if provider_override is _CONFIGURED_PROVIDER else provider_override
    model = getattr(settings, "AI_MODEL", settings.AI_MODEL_BASIC)

    try:
        async with asyncio.timeout(getattr(settings, "AI_INTERACTIVE_DEADLINE_SECONDS", 25)):
            model_styled_answer = False
            compile_started = time.perf_counter()
            if request.interaction:
                query, message = _resume_selection(request, state)
                compiled = CompileResult(query=query, deterministic=True)
            else:
                message = request.message or ""
                async with asyncio.timeout(getattr(settings, "AI_COMPILE_TIMEOUT_SECONDS", 8)):
                    compiled = await compile_query(
                        message=message, catalog=catalog, context=request.context,
                        state=state, definitions=definitions, provider=provider, model=model,
                    )
            stages["compile"] = int((time.perf_counter() - compile_started) * 1000)
            usage.add(compiled.provider)
            query = compiled.query

            if query.goal == QueryGoal.CLARIFY:
                response = _clarification(query, envelope.public_scope())
            elif query.goal == QueryGoal.GENERAL:
                response = _deterministic_general(query, envelope.public_scope(), envelope.industry)
                if response is None:
                    general_started = time.perf_counter()
                    async with asyncio.timeout(getattr(settings, "AI_ANSWER_TIMEOUT_SECONDS", 9)):
                        response, general_usage = await _general_answer(
                            message, model, provider, envelope.public_scope(),
                            style_instruction,
                        )
                    model_styled_answer = general_usage is not None
                    stages["answer"] = int((time.perf_counter() - general_started) * 1000)
                    usage.add(general_usage)
            else:
                execute_started = time.perf_counter()
                response = execute_semantic_query(db, user, query, catalog, envelope)
                stages["execute"] = int((time.perf_counter() - execute_started) * 1000)
                if response.observations:
                    synthesis_started = time.perf_counter()
                    try:
                        async with asyncio.timeout(getattr(settings, "AI_ANSWER_TIMEOUT_SECONDS", 9)):
                            response, answer_usage = await _synthesize(
                                message=message, query=query, response=response,
                                model=model, provider=provider,
                                style_instruction=style_instruction,
                            )
                        model_styled_answer = answer_usage is not None
                        usage.add(answer_usage)
                    except (TimeoutError, ValueError, TypeError, json.JSONDecodeError):
                        # The deterministic evidence-backed answer is always a
                        # complete fallback; no repair model or retry loop runs.
                        pass
                    stages["answer"] = int((time.perf_counter() - synthesis_started) * 1000)

            if not model_styled_answer:
                response = response.model_copy(update={
                    "answer": redact_internal_identifiers(
                        style_deterministic_summary(response.answer, "en", preferences),
                    ),
                })
            state = _update_state(state, request, query, response, envelope.policy_version)
            stages["total"] = int((time.perf_counter() - started) * 1000)
            return EngineResult(
                response=response, state=state, query=query, usage=usage,
                stage_durations_ms=stages,
                deterministic_compile=compiled.deterministic,
            )
    except TimeoutError:
        stages["total"] = int((time.perf_counter() - started) * 1000)
        return EngineResult(
            response=AssistantResponse(
                outcome=AssistantOutcome.UNAVAILABLE,
                answer="This turn reached the 25-second interactive deadline. No partial or unverified answer was saved; please try again.",
                scope=envelope.public_scope(),
            ),
            state=state, usage=usage, stage_durations_ms=stages,
        )
    except (ValueError, TypeError, json.JSONDecodeError):
        stages["total"] = int((time.perf_counter() - started) * 1000)
        return EngineResult(
            response=AssistantResponse(
                outcome=AssistantOutcome.UNSUPPORTED,
                answer="I couldn't map that request to the approved ERP catalog. Try naming the record, metric, group, or comparison you want.",
                scope=envelope.public_scope(),
            ),
            state=state, usage=usage, stage_durations_ms=stages,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        stages["total"] = int((time.perf_counter() - started) * 1000)
        return EngineResult(
            response=AssistantResponse(
                outcome=AssistantOutcome.UNAVAILABLE,
                answer="The assistant service is temporarily unavailable. No unverified answer was saved; please try again.",
                scope=envelope.public_scope(),
            ),
            state=state, usage=usage, stage_durations_ms=stages,
        )
