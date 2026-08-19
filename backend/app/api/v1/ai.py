"""Universal, governed Edvatiq assistant API."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import Field, ValidationError, field_validator
from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.orm import Session

from app.ai.access import AccessViolation, resolve_access_envelope
from app.ai.actions import confirm_action as execute_confirmed_action
from app.ai.actions import prepare_action as prepare_ai_action
from app.ai.actions import serialize_action, undo_action
from app.ai.catalog import CatalogError, catalog_for
from app.ai.contracts import (
    Artifact, AssistantOutcome, AssistantRequest, AssistantResponse,
    ConversationState, SemanticQuery,
)
from app.ai.definitions import semantic_definitions, validate_definitions
from app.ai.engine import EngineResult, run_assistant_turn
from app.ai.execution import execute_semantic_query
from app.ai.presentation import (
    decorate_artifact, normalize_student_navigation_refs,
    redact_internal_identifiers, sanitize_display_data,
)
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.deps import require_permissions
from app.models import (
    AIAction, AIExecutionTrace, AIMessageFeedback, AIResultSession,
    AISavedView, AISemanticPolicy, AIUsage, AIWallet, ChatConversation, ChatMessage,
    ChatTurn, Job, Organization, Setting, User,
)
from app.schemas import ChatMessageOut, ChatRequest, ConversationOut
from app.schemas.validation import RequestModel
from app.services.ai_metering import calculate_charge, route_credit_limit
from app.services.audit import log_action
from app.services.cursor_pagination import decode_cursor, encode_cursor, page_size
from app.services.rbac import user_has_permissions
from app.services.realtime import publish_change
from app.services.wallet import (
    release_reservation, reserve_credit_budget, settle_reservation,
    wallet_summary,
)

logger = logging.getLogger("edvatiq.ai")
router = APIRouter(prefix="/ai", tags=["ai"])


def _provider_free_turn(request: AssistantRequest) -> bool:
    if not request.message:
        return False
    text = " ".join(request.message.casefold().split()).strip(".! ")
    return text in {
        "hi", "hello", "hey", "vanakkam", "\u0bb5\u0ba3\u0b95\u0bcd\u0b95\u0bae\u0bcd",
        "good morning", "good afternoon", "good evening",
        "what can you do", "how can you help", "help me use",
    }


def require_ai_access(
    user: User = Depends(require_permissions("ai.use")),
    db: Session = Depends(get_db),
) -> User:
    try:
        envelope = resolve_access_envelope(db, user)
    except AccessViolation as exc:
        raise HTTPException(403, exc.message) from exc
    if "ai.use" not in envelope.permissions:
        raise HTTPException(403, "Edvatiq AI is not included in your current access")
    return user


class ConfirmAction(RequestModel):
    confirmation_token: str | None = None


class PrepareAction(RequestModel):
    action_type: str = Field(min_length=1, max_length=100, pattern="^[a-z][a-z0-9_]*$")
    payload: dict
    conversation_id: str | None = Field(default=None, max_length=100)
    idempotency_key: str = Field(min_length=8, max_length=120)


class SemanticDefinitionsUpdate(RequestModel):
    definitions: dict
    version: int | None = Field(default=None, ge=0)


class SavedViewBody(RequestModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    query_spec: dict
    layout: list = Field(default_factory=list)
    visibility: str = Field(default="private", pattern="^(private|team)$")
    version: int | None = None


class FeedbackBody(RequestModel):
    rating: str = Field(pattern="^(helpful|not_helpful)$")
    reason: str | None = Field(default=None, max_length=500)


class ResultQueryBody(RequestModel):
    query_spec: dict
    cursor: str | None = None
    limit: int = Field(default=25, ge=1, le=100)


class ConversationUpdate(RequestModel):
    title: str | None = Field(default=None, max_length=120)
    pinned: bool | None = None
    archived: bool | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str:
        if value is None or not " ".join(value.split()):
            raise ValueError("A chat title is required")
        return " ".join(value.split())


def _conversation(db: Session, user: User, conversation_id: str) -> ChatConversation:
    row = db.get(ChatConversation, conversation_id)
    if not row or row.organization_id != user.organization_id or row.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    if row.expires_at and row.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(410, "This conversation has expired")
    return row


def _conversation_summary(db: Session, conversation: ChatConversation) -> dict:
    preview = db.execute(select(ChatMessage.content).where(
        ChatMessage.conversation_id == conversation.id,
        ChatMessage.role == "user",
    ).order_by(ChatMessage.created_at.desc()).limit(1)).scalar_one_or_none()
    statuses = dict(db.execute(select(ChatTurn.status, func.count(ChatTurn.id)).where(
        ChatTurn.conversation_id == conversation.id,
    ).group_by(ChatTurn.status)).all())
    return {
        "id": conversation.id, "title": conversation.title,
        "created_at": conversation.created_at, "updated_at": conversation.updated_at,
        "preview": preview, "turn_count": sum(statuses.values()),
        "active_stream": bool(statuses.get("processing")),
        "pinned_at": conversation.pinned_at, "archived_at": conversation.archived_at,
    }


def _wallet_payload(db: Session, organization_id: str) -> dict | None:
    wallet = db.execute(select(AIWallet).where(
        AIWallet.organization_id == organization_id,
    )).scalar_one_or_none()
    return wallet_summary(wallet) if wallet else None


def _message_dict(message: ChatMessage, *, feedback_rating: str | None = None) -> dict:
    return {
        "id": message.id, "conversation_id": message.conversation_id,
        "turn_id": message.turn_id, "role": message.role,
        "content": message.content, "outcome": message.outcome,
        "artifacts": message.artifacts or [], "suggestions": message.suggestions or [],
        "evidence": message.evidence or [], "scope": message.scope or {},
        "semantic_query": message.semantic_query, "feedback_rating": feedback_rating,
        "created_at": message.created_at,
    }


def _security_allowed(envelope, security: dict, entity: str | None) -> bool:
    if not set(security.get("permissions") or []).issubset(envelope.permissions):
        return False
    domains = set(security.get("domains") or [])
    if any(not envelope.domain_available(domain) for domain in domains):
        return False
    identifiers = [str(value) for value in security.get("entity_ids") or [] if value]
    entity_refs = security.get("entity_refs") or []
    labelled_scope = security.get("scope") or {}
    if labelled_scope.get("historical"):
        # Legacy blocks predate field/domain labels and cannot be safely
        # reauthorized. Keep the turn, but require a fresh governed answer.
        return False
    location_ids = {str(value) for value in labelled_scope.get("location_ids") or [] if value}
    client_ids = {str(value) for value in labelled_scope.get("client_ids") or [] if value}
    if envelope.location_ids is not None and not location_ids.issubset(envelope.location_ids):
        return False
    if envelope.client_ids is not None and not client_ids.issubset(envelope.client_ids):
        return False
    for ref in entity_refs:
        kind = ref.get("kind") if isinstance(ref, dict) else getattr(ref, "kind", None)
        identifier = ref.get("id") if isinstance(ref, dict) else getattr(ref, "id", None)
        if not identifier:
            continue
        try:
            if not envelope.module_enabled(catalog_for(envelope.industry).entity(kind).module):
                return False
        except CatalogError:
            return False
        if kind == "student" and not envelope.allows_student(str(identifier), domains):
            return False
        if kind == "client" and envelope.client_ids is not None and str(identifier) not in envelope.client_ids:
            return False
    if entity_refs:
        return True
    if entity == "student":
        return all(envelope.allows_student(identifier, domains) for identifier in identifiers)
    if entity == "client" and envelope.client_ids is not None:
        return set(identifiers).issubset(envelope.client_ids)
    return True


def _history_query_allowed(envelope, value: dict | None) -> bool:
    if not value:
        return True
    try:
        query = SemanticQuery.model_validate(value)
        if query.entity == "assistant":
            return True
        catalog = catalog_for(envelope.industry)
        catalog.validate(query)
        envelope.require_query(catalog, query)
        _, unavailable = envelope.projectable_fields(catalog, query)
        if unavailable:
            return False
        domains = set()
        field_keys = set(query.fields) | set(query.group_by)
        field_keys.update(item.field for item in query.filters)
        field_keys.update(item.field for item in query.sort)
        for key in field_keys:
            domains.update(catalog.field(query.entity, key).domains)
        for key in query.metrics:
            domains.update(catalog.metric(key).domains)
        for ref in query.entities:
            definition = catalog.entity(ref.kind)
            if not envelope.module_enabled(definition.module):
                return False
            if ref.kind == "student" and ref.id and not envelope.allows_student(ref.id, domains):
                return False
            if ref.kind == "client" and ref.id and envelope.client_ids is not None and ref.id not in envelope.client_ids:
                return False
        return True
    except (AccessViolation, CatalogError, ValidationError, ValueError):
        return False


def _authorized_message_dict(
    db: Session, user: User, message: ChatMessage,
    *, feedback_rating: str | None = None,
) -> dict:
    result = _message_dict(message, feedback_rating=feedback_rating)
    if message.role != "assistant":
        return result
    try:
        envelope = resolve_access_envelope(db, user)
    except AccessViolation:
        envelope = None
    if envelope is None or "ai.use" not in envelope.permissions:
        allowed_artifacts, allowed_suggestions = [], []
        answer_allowed = False
    else:
        entity = (message.semantic_query or {}).get("entity")
        module_available = True
        if entity and entity != "assistant":
            try:
                module_available = envelope.module_enabled(catalog_for(envelope.industry).entity(entity).module)
            except CatalogError:
                module_available = False
        meta = message.meta or {}
        scope_changed = (
            int(meta.get("access_version", user.access_version)) != int(user.access_version)
            or int(meta.get("policy_version", envelope.policy_version)) != int(envelope.policy_version)
        )
        answer_allowed = (
            module_available
            and _history_query_allowed(envelope, message.semantic_query)
            and not (scope_changed and entity and entity != "assistant")
        )

        def allowed(item: dict) -> bool:
            item_security = item.get("security") or {}
            if not module_available:
                return False
            # Population totals and aggregates cannot be safely reinterpreted
            # after a scope change; force a fresh authorized execution.
            if scope_changed and item_security.get("scope"):
                return False
            return _security_allowed(envelope, item_security, entity)

        allowed_artifacts = [item for item in result["artifacts"] if allowed(item)]
        allowed_suggestions = [item for item in result["suggestions"] if allowed(item)]
    safe_allowed_suggestions = [{
        **item,
        "label": redact_internal_identifiers(item.get("label") or ""),
        "prompt": redact_internal_identifiers(item.get("prompt") or ""),
    } for item in allowed_suggestions]
    if not answer_allowed or len(allowed_artifacts) != len(result["artifacts"]):
        return {
            **result,
            "content": "This historical answer is no longer available under your current access. Ask again for a freshly authorized answer.",
            "outcome": AssistantOutcome.ACCESS_LIMITED.value,
            "artifacts": [], "suggestions": safe_allowed_suggestions, "evidence": [],
        }
    safe_artifacts = []
    query = None
    if message.semantic_query:
        try:
            query = SemanticQuery.model_validate(message.semantic_query)
        except ValidationError:
            query = None
    if query and envelope:
        catalog = catalog_for(envelope.industry)
        try:
            typed_artifacts = [Artifact.model_validate(item) for item in allowed_artifacts]
            if db is not None and envelope.industry == "college":
                typed_artifacts = normalize_student_navigation_refs(
                    db, envelope.organization_id, typed_artifacts,
                )
            safe_artifacts = [
                decorate_artifact(item, query, catalog).model_dump(mode="json")
                for item in typed_artifacts
            ]
        except (CatalogError, ValidationError, ValueError):
            safe_artifacts = []
    elif not allowed_artifacts:
        safe_artifacts = []

    if len(safe_artifacts) != len(allowed_artifacts):
        return {
            **result,
            "content": "This historical answer needs to be refreshed before it can be displayed safely. Ask again for a current, authorized answer.",
            "outcome": AssistantOutcome.ACCESS_LIMITED.value,
            "artifacts": [], "suggestions": [], "evidence": [],
        }
    safe_evidence = [
        sanitize_display_data(item, preserve_controls=False)
        for item in result["evidence"]
        if isinstance(item, dict)
    ]
    return {
        **result,
        "content": redact_internal_identifiers(result["content"]),
        "artifacts": safe_artifacts,
        "suggestions": safe_allowed_suggestions,
        "evidence": safe_evidence,
    }


def _conversation_statement(user: User, scope: str, query_text: str | None):
    now = datetime.now(timezone.utc)
    preview = select(ChatMessage.content).where(
        ChatMessage.conversation_id == ChatConversation.id,
        ChatMessage.role == "user",
    ).order_by(ChatMessage.created_at.desc()).limit(1).correlate(ChatConversation).scalar_subquery()
    turn_count = select(func.count(ChatTurn.id)).where(
        ChatTurn.conversation_id == ChatConversation.id,
    ).correlate(ChatConversation).scalar_subquery()
    active_stream = select(func.count(ChatTurn.id) > 0).where(
        ChatTurn.conversation_id == ChatConversation.id,
        ChatTurn.status == "processing",
    ).correlate(ChatConversation).scalar_subquery()
    statement = select(ChatConversation, preview, turn_count, active_stream).where(
        ChatConversation.organization_id == user.organization_id,
        ChatConversation.user_id == user.id,
        or_(ChatConversation.expires_at.is_(None), ChatConversation.expires_at > now),
    )
    if scope == "active":
        statement = statement.where(ChatConversation.archived_at.is_(None))
    elif scope == "archived":
        statement = statement.where(ChatConversation.archived_at.is_not(None))
    search = " ".join((query_text or "").split())
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        message_match = select(ChatMessage.id).where(
            ChatMessage.conversation_id == ChatConversation.id,
            ChatMessage.content.ilike(pattern, escape="\\"),
        ).exists()
        statement = statement.where(or_(
            ChatConversation.title.ilike(pattern, escape="\\"), message_match,
        ))
    return statement


def _conversation_row(row) -> dict:
    conversation, preview, count, active = row
    return {
        "id": conversation.id, "title": conversation.title,
        "created_at": conversation.created_at, "updated_at": conversation.updated_at,
        "preview": preview, "turn_count": count, "active_stream": bool(active),
        "pinned_at": conversation.pinned_at, "archived_at": conversation.archived_at,
    }


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    scope: str = Query(default="active", pattern="^(active|archived|all)$"),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_ai_access), db: Session = Depends(get_db),
):
    rows = db.execute(_conversation_statement(user, scope, q).order_by(
        ChatConversation.pinned_at.desc().nullslast(), ChatConversation.updated_at.desc(),
    ).limit(limit)).all()
    return [_conversation_row(row) for row in rows]


@router.get("/conversations/page")
def conversation_page(
    scope: str = Query(default="active", pattern="^(active|archived|all)$"),
    q: str | None = Query(default=None, max_length=120), cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    user: User = Depends(require_ai_access), db: Session = Depends(get_db),
):
    search = " ".join((q or "").split())
    filters = {"scope": scope, "q": search.casefold()}
    values = decode_cursor(cursor, scope="ai.conversations", organization_id=user.organization_id, filters=filters)
    statement = _conversation_statement(user, scope, search)
    pin_rank = case((ChatConversation.pinned_at.is_not(None), 1), else_=0)
    sort_at = func.coalesce(ChatConversation.pinned_at, ChatConversation.updated_at)
    if values:
        rank, pivot_at, identifier = int(values["rank"]), datetime.fromisoformat(str(values["at"])), str(values["id"])
        statement = statement.where(or_(
            pin_rank < rank,
            and_(pin_rank == rank, sort_at < pivot_at),
            and_(pin_rank == rank, sort_at == pivot_at, ChatConversation.id < identifier),
        ))
    size = page_size(limit)
    rows = list(db.execute(statement.order_by(
        pin_rank.desc(), sort_at.desc(), ChatConversation.id.desc(),
    ).limit(size + 1)).all())
    has_more = len(rows) > size
    rows = rows[:size]
    next_cursor = None
    if has_more and rows:
        last = rows[-1][0]
        next_cursor = encode_cursor(
            scope="ai.conversations", organization_id=user.organization_id, filters=filters,
            values={"rank": 1 if last.pinned_at else 0, "at": (last.pinned_at or last.updated_at).isoformat(), "id": last.id},
        )
    return {"items": [_conversation_row(row) for row in rows], "next_cursor": next_cursor, "has_more": has_more}


@router.get("/conversations/{cid}", response_model=ConversationOut)
def get_conversation(cid: str, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    return _conversation_summary(db, _conversation(db, user, cid))


def _feedback_ratings(db: Session, user: User, rows: list[ChatMessage]) -> dict:
    if not rows:
        return {}
    return dict(db.execute(select(AIMessageFeedback.message_id, AIMessageFeedback.rating).where(
        AIMessageFeedback.user_id == user.id,
        AIMessageFeedback.message_id.in_([row.id for row in rows]),
    )).all())


@router.get("/conversations/{cid}/messages", response_model=list[ChatMessageOut])
def get_messages(cid: str, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    conversation = _conversation(db, user, cid)
    rows = list(db.execute(select(ChatMessage).where(
        ChatMessage.conversation_id == conversation.id,
    ).order_by(ChatMessage.created_at, ChatMessage.id)).scalars())
    ratings = _feedback_ratings(db, user, rows)
    return [_authorized_message_dict(db, user, row, feedback_rating=ratings.get(row.id)) for row in rows]


@router.get("/conversations/{cid}/messages/page")
def message_page(
    cid: str, cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_ai_access), db: Session = Depends(get_db),
):
    conversation = _conversation(db, user, cid)
    values = decode_cursor(cursor, scope=f"ai.messages:{conversation.id}", organization_id=user.organization_id)
    statement = select(ChatMessage).where(ChatMessage.conversation_id == conversation.id)
    if values:
        pivot_at = datetime.fromisoformat(str(values["at"]))
        statement = statement.where(or_(
            ChatMessage.created_at < pivot_at,
            and_(ChatMessage.created_at == pivot_at, ChatMessage.id < str(values["id"])),
        ))
    size = page_size(limit, default=50)
    rows = list(db.execute(statement.order_by(
        ChatMessage.created_at.desc(), ChatMessage.id.desc(),
    ).limit(size + 1)).scalars())
    has_more = len(rows) > size
    rows = rows[:size]
    oldest = rows[-1] if rows else None
    ratings = _feedback_ratings(db, user, rows)
    next_cursor = encode_cursor(
        scope=f"ai.messages:{conversation.id}", organization_id=user.organization_id,
        values={"at": oldest.created_at.isoformat(), "id": oldest.id},
    ) if has_more and oldest else None
    return {
        "items": [_authorized_message_dict(db, user, row, feedback_rating=ratings.get(row.id)) for row in reversed(rows)],
        "next_cursor": next_cursor, "has_more": has_more,
    }


@router.patch("/conversations/{cid}", response_model=ConversationOut)
def update_conversation(
    cid: str, body: ConversationUpdate,
    user: User = Depends(require_ai_access), db: Session = Depends(get_db),
):
    fields = body.model_fields_set & {"title", "pinned", "archived"}
    if not fields:
        raise HTTPException(422, "Choose a conversation change")
    if body.archived is True and body.pinned is True:
        raise HTTPException(422, "An archived chat cannot be pinned")
    conversation = _conversation(db, user, cid)
    processing = bool(db.scalar(select(func.count(ChatTurn.id)).where(
        ChatTurn.conversation_id == conversation.id, ChatTurn.status == "processing",
    )))
    if "archived" in fields and body.archived and processing:
        raise HTTPException(409, "Wait for the current answer to finish before archiving this chat")
    if "archived" in fields:
        conversation.archived_at = datetime.now(timezone.utc) if body.archived else None
        if body.archived:
            conversation.pinned_at = None
    if "pinned" in fields:
        if body.pinned and conversation.archived_at:
            raise HTTPException(409, "Restore this chat before pinning it")
        conversation.pinned_at = datetime.now(timezone.utc) if body.pinned else None
    if "title" in fields:
        conversation.title = body.title
    log_action(db, organization_id=user.organization_id, user_id=user.id,
               action="ai.conversation.update", resource_type="conversation",
               resource_id=conversation.id, meta={"fields": sorted(fields)})
    db.commit()
    db.refresh(conversation)
    return _conversation_summary(db, conversation)


def _display_request(request: AssistantRequest) -> str:
    if request.message:
        return request.message
    return request.interaction.entity.label or "Selected record"


def _new_conversation(db: Session, user: User, request: AssistantRequest) -> ChatConversation:
    retention = db.execute(select(Setting).where(
        Setting.organization_id == user.organization_id,
        Setting.key == "ai.conversation_retention_days",
    )).scalar_one_or_none()
    retention_days = max(1, min(int((retention.value or {}).get("days", 90)), 3650)) if retention else 90
    title = " ".join(_display_request(request).split())[:60] or "New chat"
    row = ChatConversation(
        organization_id=user.organization_id, user_id=user.id, title=title,
        provider="openai" if settings.AI_API_KEY else "local", model=settings.AI_MODEL,
        expires_at=datetime.now(timezone.utc) + timedelta(days=retention_days), state={},
    )
    db.add(row)
    db.flush()
    return row


def _attach_result_session(
    db: Session, user: User, conversation: ChatConversation,
    query: SemanticQuery | None, response: AssistantResponse,
) -> None:
    if not query:
        return
    artifact = next((item for item in response.artifacts if item.type in {"records", "ranking"} and item.data.get("has_more")), None)
    if not artifact:
        return
    row = AIResultSession(
        organization_id=user.organization_id, user_id=user.id,
        conversation_id=conversation.id, entity=query.entity,
        query_spec=artifact.data.get("query") or query.model_dump(mode="json"),
        result_type=artifact.type, total_count=int(artifact.data.get("total") or 0),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    db.add(row)
    db.flush()
    artifact.data = {**artifact.data, "result_session_id": row.id}
    response.result_session_id = row.id


def _queue_background_analysis(
    db: Session,
    user: User,
    conversation: ChatConversation,
    turn: ChatTurn,
    query: SemanticQuery | None,
    response: AssistantResponse,
    access_version: int,
    policy_version: int,
) -> None:
    if response.outcome != AssistantOutcome.PROCESSING or not query:
        return
    job = Job(
        organization_id=user.organization_id,
        kind="ai_semantic_analysis",
        payload={
            "user_id": user.id,
            "conversation_id": conversation.id,
            "turn_id": turn.id,
            "semantic_query": query.model_dump(mode="json"),
            "access_version": access_version,
            "policy_version": policy_version,
        },
        status="queued",
        run_at=datetime.now(timezone.utc),
        max_attempts=3,
        idempotency_key=f"ai-analysis:{turn.id}",
    )
    db.add(job)
    db.flush()
    for artifact in response.artifacts:
        if artifact.type == "processing":
            artifact.data = {**artifact.data, "job_id": job.id, "status": "queued"}


def _quota_result(state: dict | None, scope) -> EngineResult:
    try:
        conversation_state = ConversationState.model_validate(state or {})
    except ValidationError:
        conversation_state = ConversationState()
    return EngineResult(
        response=AssistantResponse(
            outcome=AssistantOutcome.QUOTA_EXHAUSTED,
            answer="Your organization has no AI credits available for this turn. Recharge or wait for the next credit cycle.",
            scope=scope,
        ),
        state=conversation_state,
    )


def _entitlement_result(state: dict | None, scope) -> EngineResult:
    try:
        conversation_state = ConversationState.model_validate(state or {})
    except ValidationError:
        conversation_state = ConversationState()
    return EngineResult(
        response=AssistantResponse(
            outcome=AssistantOutcome.ENTITLEMENT_REQUIRED,
            answer="Edvatiq AI is not enabled for your organization's current subscription.",
            scope=scope,
        ),
        state=conversation_state,
    )


async def _process_chat(body: ChatRequest, user: User, db: Session, emit=None):
    started = perf_counter()
    request = AssistantRequest.model_validate(body.model_dump(exclude_none=True))
    key = request.idempotency_key or f"ai:{user.id}:{secrets.token_urlsafe(16)}"
    lock_key = f"ai-turn:{user.organization_id}:{user.id}:{key}"
    if db.get_bind().dialect.name == "postgresql":
        db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(lock_key, 0))))

    existing_turn = db.execute(select(ChatTurn).where(
        ChatTurn.organization_id == user.organization_id,
        ChatTurn.user_id == user.id, ChatTurn.request_key == key,
    )).scalar_one_or_none()
    if existing_turn and existing_turn.status == "completed":
        existing_message = db.execute(select(ChatMessage).where(
            ChatMessage.turn_id == existing_turn.id, ChatMessage.role == "assistant",
        )).scalar_one_or_none()
        if existing_message:
            conversation = _conversation(db, user, existing_message.conversation_id)
            return {
                "conversation_id": conversation.id,
                "conversation": _conversation_summary(db, conversation),
                "message": _authorized_message_dict(db, user, existing_message),
                "credits_used": 0, "ai_wallet": _wallet_payload(db, user.organization_id),
            }
    if existing_turn and existing_turn.status == "processing":
        raise HTTPException(409, "This request is already being processed")

    conversation = None
    if existing_turn:
        conversation = _conversation(db, user, existing_turn.conversation_id)
        db.execute(delete(ChatMessage).where(ChatMessage.turn_id == existing_turn.id))
        existing_turn.status, existing_turn.error_code, existing_turn.completed_at = "processing", None, None
    elif request.conversation_id:
        conversation = _conversation(db, user, request.conversation_id)
    if conversation and conversation.archived_at:
        raise HTTPException(409, "Restore this chat before continuing it")
    conversation = conversation or _new_conversation(db, user, request)
    turn = existing_turn or ChatTurn(
        organization_id=user.organization_id, conversation_id=conversation.id,
        user_id=user.id, request_key=key, status="processing",
    )
    if not existing_turn:
        db.add(turn)
        db.flush()

    initial_access_version = int(user.access_version)
    initial_envelope = resolve_access_envelope(db, user)
    db.add(ChatMessage(
        organization_id=user.organization_id, conversation_id=conversation.id,
        turn_id=turn.id, role="user", content=_display_request(request),
        meta={
            "idempotency_key": key,
            "interaction": request.interaction.model_dump(mode="json") if request.interaction else None,
            "context": request.context.model_dump(mode="json") if request.context else None,
        },
    ))
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()

    reservation_id = None
    result = (
        None if initial_envelope.module_enabled("ai")
        else _entitlement_result(conversation.state, initial_envelope.public_scope())
    )
    try:
        if emit:
            await emit("status", {"message": "Understanding your request"})
        if settings.AI_API_KEY and not _provider_free_turn(request):
            organization = db.get(Organization, user.organization_id)
            try:
                reservation = reserve_credit_budget(
                    db, organization, route_credit_limit(db, "analytics"), key,
                )
                db.flush()
                reservation_id = reservation.id
                db.commit()
            except HTTPException as exc:
                db.rollback()
                if exc.status_code != 402:
                    raise
                result = _quota_result(conversation.state, initial_envelope.public_scope())

        if result is None:
            result = await run_assistant_turn(
                request=request, user=user, db=db, conversation_state=conversation.state,
            )

        db.expire(user, ["access_version", "is_active"])
        current_access_version = db.execute(select(User.access_version).where(
            User.id == user.id,
        ).with_for_update()).scalar_one()
        current_envelope = resolve_access_envelope(db, user, fresh=True)
        if not current_envelope.module_enabled("ai"):
            result = _entitlement_result(conversation.state, current_envelope.public_scope())
        elif (
            current_access_version != initial_access_version
            or current_envelope.policy_version != initial_envelope.policy_version
            or "ai.use" not in current_envelope.permissions
        ):
            result = EngineResult(
                response=AssistantResponse(
                    outcome=AssistantOutcome.ACCESS_LIMITED,
                    answer="Your access changed while this answer was being prepared. Ask again for a current, authorized answer.",
                    scope=current_envelope.public_scope(),
                ),
                state=ConversationState(), stage_durations_ms=result.stage_durations_ms,
                usage=result.usage,
            )

        response = result.response
        _attach_result_session(db, user, conversation, result.query, response)
        _queue_background_analysis(
            db, user, conversation, turn, result.query, response,
            current_access_version, current_envelope.policy_version,
        )
        response_data = response.model_dump(mode="json")
        assistant = ChatMessage(
            organization_id=user.organization_id, conversation_id=conversation.id,
            turn_id=turn.id, role="assistant", content=response.answer,
            outcome=response.outcome.value, artifacts=response_data["artifacts"],
            suggestions=response_data["suggestions"], evidence=response_data["observations"],
            scope=response_data.get("scope") or {},
            semantic_query=result.query.model_dump(mode="json") if result.query else None,
            meta={"request_key": key, "access_version": current_access_version,
                  "policy_version": current_envelope.policy_version},
        )
        db.add(assistant)
        conversation.state = result.state.model_dump(mode="json")
        conversation.updated_at = datetime.now(timezone.utc)
        turn.status, turn.completed_at, turn.error_code = "completed", datetime.now(timezone.utc), None

        usage = {
            "input_tokens": result.usage.input_tokens,
            "cached_input_tokens": result.usage.cached_input_tokens,
            "output_tokens": result.usage.output_tokens,
            "embedding_tokens": 0, "provider_requests": result.usage.provider_requests,
        }
        charge = calculate_charge(db, settings.AI_MODEL, usage)
        settled_wallet = None
        if reservation_id:
            from app.models import WalletReservation

            reservation = db.get(WalletReservation, reservation_id)
            settled_wallet = settle_reservation(db, reservation, charge.credits) if charge.credits else release_reservation(db, reservation)
        if result.usage.provider_requests:
            db.add(AIUsage(
                organization_id=user.organization_id, user_id=user.id,
                model=settings.AI_MODEL, input_tokens=result.usage.input_tokens,
                cached_input_tokens=result.usage.cached_input_tokens,
                output_tokens=result.usage.output_tokens, embedding_tokens=0,
                provider_requests=result.usage.provider_requests,
                provider_cost_paise=charge.provider_cost_paise, rate_version=charge.rate_version,
                tool_calls=1 if result.query else 0,
                latency_ms=int((perf_counter() - started) * 1000),
                route=result.query.goal.value if result.query else "assistant",
                status="completed", credits_used=charge.credits,
                tool_latency_ms=result.stage_durations_ms.get("execute", 0),
            ))
        db.add(AIExecutionTrace(
            organization_id=user.organization_id, user_id=user.id,
            conversation_id=conversation.id, turn_id=turn.id,
            route=result.query.goal.value if result.query else "assistant",
            outcome=response.outcome.value,
            semantic_query=result.query.model_dump(mode="json") if result.query else None,
            scope=response_data.get("scope") or {},
            stage_durations_ms=result.stage_durations_ms,
            provider_requests=result.usage.provider_requests,
            input_tokens=result.usage.input_tokens,
            cached_input_tokens=result.usage.cached_input_tokens,
            output_tokens=result.usage.output_tokens, embedding_tokens=0,
            total_latency_ms=int((perf_counter() - started) * 1000),
            zero_credit=charge.credits == 0,
        ))
        log_action(db, organization_id=user.organization_id, user_id=user.id,
                   action="ai.chat", resource_type="conversation", resource_id=conversation.id,
                   meta={"goal": result.query.goal.value if result.query else None,
                         "outcome": response.outcome.value})
        db.commit()
        db.refresh(assistant)
        if emit:
            await emit("answer_delta", {"text": response.answer})
            for artifact in response_data["artifacts"]:
                await emit("artifact", artifact)
            for suggestion in response_data["suggestions"]:
                await emit("suggestion", suggestion)
        if settled_wallet:
            try:
                await asyncio.to_thread(publish_change, str(user.organization_id), "/ai/wallet")
            except Exception as exc:
                logger.warning("ai_wallet_publish_failed organization=%s error_type=%s", user.organization_id, type(exc).__name__)
        return {
            "conversation_id": conversation.id,
            "conversation": _conversation_summary(db, conversation),
            "message": _authorized_message_dict(db, user, assistant),
            "credits_used": charge.credits,
            "ai_wallet": wallet_summary(settled_wallet) if settled_wallet else _wallet_payload(db, user.organization_id),
        }
    except (Exception, asyncio.CancelledError) as exc:
        db.rollback()
        if reservation_id:
            from app.models import WalletReservation

            reservation = db.get(WalletReservation, reservation_id)
            if reservation and reservation.status == "reserved":
                release_reservation(db, reservation)
        failed_turn = db.get(ChatTurn, turn.id)
        if failed_turn:
            failed_turn.status = "cancelled" if isinstance(exc, asyncio.CancelledError) else "failed"
            failed_turn.error_code = "cancelled" if isinstance(exc, asyncio.CancelledError) else type(exc).__name__[:80]
        db.commit()
        raise


@router.post("/chat")
async def chat(body: ChatRequest, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    try:
        return await _process_chat(body, user, db)
    except HTTPException:
        raise
    except Exception:
        logger.exception("ai_chat_failed organization=%s user=%s", user.organization_id, user.id)
        raise HTTPException(502, "Edvatiq could not complete that request. Please try again.")


def _event(name: str, payload: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, default=str)}\n\n"


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, user: User = Depends(require_ai_access)):
    stream_user_id, stream_organization_id = user.id, user.organization_id

    async def events():
        queue = asyncio.Queue()

        async def emit(name, payload):
            await queue.put((name, payload))

        async def produce():
            try:
                with SessionLocal() as stream_db:
                    stream_user = stream_db.get(User, stream_user_id)
                    if not stream_user or not stream_user.is_active or stream_user.organization_id != stream_organization_id:
                        raise HTTPException(401, "Authentication session is no longer active")
                    if not user_has_permissions(stream_db, stream_user, ["ai.use"]):
                        raise HTTPException(403, "Edvatiq AI access is no longer available")
                    result = await _process_chat(body, stream_user, stream_db, emit=emit)
                await emit("complete", result)
            except Exception as exc:
                if not isinstance(exc, HTTPException):
                    logger.exception("ai_stream_failed organization=%s user=%s", stream_organization_id, stream_user_id)
                await emit("error", {
                    "message": exc.detail if isinstance(exc, HTTPException) and isinstance(exc.detail, str) else "Edvatiq could not complete that request.",
                    "code": f"http_{exc.status_code}" if isinstance(exc, HTTPException) else "assistant_unavailable",
                    "stage": "request" if isinstance(exc, HTTPException) else "execution",
                    "retryable": not isinstance(exc, HTTPException) or exc.status_code in {408, 409, 429} or exc.status_code >= 500,
                })
            finally:
                await queue.put(("done", None))

        producer = asyncio.create_task(produce())
        try:
            yield _event("accepted", {"request_id": body.idempotency_key})
            while True:
                try:
                    name, payload = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if name == "done":
                    break
                yield _event(name, payload)
        finally:
            if not producer.done():
                producer.cancel()
            with suppress(asyncio.CancelledError):
                await producer
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _validate_query_spec(spec: dict) -> SemanticQuery:
    try:
        return SemanticQuery.model_validate(spec)
    except ValidationError as exc:
        raise HTTPException(422, "Unsupported semantic query") from exc


def _run_query_page(
    db: Session, user: User, query_spec: dict, result_type: str,
    cursor: str | None, limit: int,
) -> dict:
    query = _validate_query_spec(query_spec)
    filters = {"query_spec": query.model_dump(mode="json"), "result_type": result_type}
    values = decode_cursor(cursor, scope="ai.results", organization_id=user.organization_id, filters=filters)
    try:
        offset = max(0, int((values or {}).get("offset", 0)))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "The pagination cursor is invalid") from exc
    size = page_size(limit, default=25, maximum=100)
    paged_query = query.model_copy(update={"limit": size})
    envelope = resolve_access_envelope(db, user)
    catalog = catalog_for(envelope.industry)
    response = execute_semantic_query(db, user, paged_query, catalog, envelope, offset=offset)
    artifact = next((item for item in response.artifacts if isinstance(item.data.get("items"), list)), None)
    if artifact and db is not None and envelope.industry == "college":
        artifact = normalize_student_navigation_refs(
            db, envelope.organization_id, [artifact],
        )[0]
    if artifact:
        artifact = decorate_artifact(artifact, query, catalog)
    items = artifact.data["items"] if artifact else []
    total = int((artifact.data.get("total") if artifact else 0) or 0)
    next_offset, has_more = offset + len(items), offset + len(items) < total
    return {
        "items": items, "total": total,
        "next_cursor": encode_cursor(
            scope="ai.results", organization_id=user.organization_id,
            values={"offset": next_offset}, filters=filters,
        ) if has_more else None,
        "has_more": has_more, "query_spec": query.model_dump(mode="json"),
        "result_type": result_type, "outcome": response.outcome.value,
        "title": artifact.title if artifact else None,
        "presentation": (
            artifact.presentation.model_dump(mode="json")
            if artifact and artifact.presentation else None
        ),
        "scope_label": artifact.data.get("scope_label") if artifact else None,
        "notice": response.answer if response.outcome != AssistantOutcome.SUCCESS else None,
    }


@router.get("/results/{session_id}")
def result_page(
    session_id: str, cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    user: User = Depends(require_ai_access), db: Session = Depends(get_db),
):
    row = db.get(AIResultSession, session_id)
    if not row or row.organization_id != user.organization_id or row.user_id != user.id:
        raise HTTPException(404, "Result not found")
    if row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(410, "This result has expired")
    return _run_query_page(db, user, row.query_spec, row.result_type, cursor, limit)


@router.post("/results/run")
def run_result_query(body: ResultQueryBody, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    query = _validate_query_spec(body.query_spec)
    return _run_query_page(db, user, query.model_dump(mode="json"), query.entity, body.cursor, body.limit)


def _view_dict(row: AISavedView) -> dict:
    return {key: getattr(row, key) for key in [
        "id", "name", "description", "query_spec", "layout", "visibility",
        "version", "owner_user_id", "updated_at",
    ]}


def _require_team_view_access(db: Session, user: User) -> None:
    from app.services.entitlements import entitlement_value
    organization = db.get(Organization, user.organization_id)
    if not user_has_permissions(db, user, ["ai.views.share"]) or not entitlement_value(db, organization, "ai.views.share", False):
        raise HTTPException(403, "Team sharing is not included in your access and plan")


@router.get("/views")
def list_views(user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    rows = db.execute(select(AISavedView).where(
        AISavedView.organization_id == user.organization_id, AISavedView.is_active.is_(True),
        or_(AISavedView.owner_user_id == user.id, AISavedView.visibility == "team"),
    ).order_by(AISavedView.updated_at.desc())).scalars()
    return [_view_dict(row) for row in rows]


def _authorize_saved_query(db: Session, user: User, spec: dict) -> SemanticQuery:
    query = _validate_query_spec(spec)
    envelope = resolve_access_envelope(db, user)
    catalog = catalog_for(envelope.industry)
    try:
        catalog.validate(query)
        envelope.require_query(catalog, query)
    except CatalogError as exc:
        raise HTTPException(422, "Unsupported semantic query") from exc
    except AccessViolation as exc:
        raise HTTPException(403, exc.message) from exc
    return query


@router.post("/views", status_code=201)
def create_view(body: SavedViewBody, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    if body.visibility == "team":
        _require_team_view_access(db, user)
    _authorize_saved_query(db, user, body.query_spec)
    row = AISavedView(organization_id=user.organization_id, owner_user_id=user.id,
                      **body.model_dump(exclude={"version"}, exclude_none=True))
    db.add(row)
    db.commit()
    db.refresh(row)
    return _view_dict(row)


@router.patch("/views/{view_id}")
def update_view(view_id: str, body: SavedViewBody, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    row = db.get(AISavedView, view_id)
    if not row or row.organization_id != user.organization_id:
        raise HTTPException(404, "View not found")
    if row.owner_user_id != user.id:
        raise HTTPException(403, "Only the owner can edit this view")
    if body.version != row.version:
        raise HTTPException(409, "This view changed. Refresh and try again")
    if body.visibility == "team":
        _require_team_view_access(db, user)
    _authorize_saved_query(db, user, body.query_spec)
    for key, value in body.model_dump(exclude={"version"}).items():
        setattr(row, key, value)
    row.version += 1
    db.commit()
    return _view_dict(row)


@router.delete("/views/{view_id}")
def delete_view(view_id: str, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    row = db.get(AISavedView, view_id)
    if not row or row.organization_id != user.organization_id:
        raise HTTPException(404, "View not found")
    if row.owner_user_id != user.id:
        raise HTTPException(403, "Only the owner can remove this view")
    row.is_active, row.version = False, row.version + 1
    db.commit()
    return {"ok": True}


@router.post("/views/{view_id}/run")
def run_view(view_id: str, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    row = db.get(AISavedView, view_id)
    if not row or row.organization_id != user.organization_id or (row.owner_user_id != user.id and row.visibility != "team"):
        raise HTTPException(404, "View not found")
    return {"view": _view_dict(row), "result": _run_query_page(db, user, row.query_spec, "saved_view", None, 25)}


@router.get("/definitions")
def get_semantic_definitions(
    user: User = Depends(require_ai_access),
    db: Session = Depends(get_db),
):
    row = db.execute(select(AISemanticPolicy).where(
        AISemanticPolicy.organization_id == user.organization_id,
    )).scalar_one_or_none()
    return {
        "definitions": semantic_definitions(db, user.organization_id),
        "version": row.version if row else 0,
    }


@router.put("/definitions")
def update_semantic_definitions(
    body: SemanticDefinitionsUpdate,
    user: User = Depends(require_permissions("roles.manage", "ai.use")),
    db: Session = Depends(get_db),
):
    try:
        definitions = validate_definitions(body.definitions)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    row = db.execute(select(AISemanticPolicy).where(
        AISemanticPolicy.organization_id == user.organization_id,
    ).with_for_update()).scalar_one_or_none()
    if row and body.version is not None and row.version != body.version:
        raise HTTPException(409, "Assistant definitions changed. Reload before saving again.")
    if not row:
        if body.version not in {None, 0}:
            raise HTTPException(409, "Assistant definitions changed. Reload before saving again.")
        row = AISemanticPolicy(
            organization_id=user.organization_id,
            definitions=definitions,
            updated_by_user_id=user.id,
        )
        db.add(row)
    else:
        row.definitions = definitions
        row.updated_by_user_id = user.id
        row.version += 1
    db.flush()
    log_action(
        db, organization_id=user.organization_id, user_id=user.id,
        action="ai.definitions.update", resource_type="ai_semantic_policy",
        resource_id=row.id, changes={"definitions": definitions},
    )
    db.commit()
    return {"definitions": definitions, "version": row.version}


@router.get("/actions")
def list_actions(user: User = Depends(require_permissions("ai.actions")), db: Session = Depends(get_db)):
    rows = db.execute(select(AIAction).where(
        AIAction.organization_id == user.organization_id, AIAction.user_id == user.id,
    ).order_by(AIAction.created_at.desc()).limit(100)).scalars()
    return [serialize_action(row) for row in rows]


@router.post("/actions/prepare")
def prepare(
    body: PrepareAction,
    user: User = Depends(require_permissions("ai.actions")),
    db: Session = Depends(get_db),
):
    if body.conversation_id:
        _conversation(db, user, body.conversation_id)
    result = prepare_ai_action(
        db, user, body.action_type, body.payload, body.conversation_id,
        idempotency_key=body.idempotency_key,
    )
    if result.get("access_denied"):
        raise HTTPException(403, result["message"])
    if result.get("error"):
        raise HTTPException(422, result["error"])
    db.commit()
    return result


def _action(db: Session, user: User, action_id: str) -> AIAction:
    row = db.get(AIAction, action_id)
    if not row or row.organization_id != user.organization_id:
        raise HTTPException(404, "Action not found")
    return row


@router.post("/actions/{action_id}/confirm")
def confirm(action_id: str, body: ConfirmAction, user: User = Depends(require_permissions("ai.actions")), db: Session = Depends(get_db)):
    result = execute_confirmed_action(db, user, _action(db, user, action_id), body.confirmation_token)
    db.commit()
    return result


@router.post("/actions/{action_id}/confirmation")
def renew_confirmation(action_id: str, user: User = Depends(require_permissions("ai.actions")), db: Session = Depends(get_db)):
    action = _action(db, user, action_id)
    if action.user_id != user.id or action.status != "pending_confirmation":
        raise HTTPException(409, "This action is not waiting for confirmation")
    if not action.required_permission or not user_has_permissions(db, user, [action.required_permission]):
        raise HTTPException(403, "Access denied")
    token = secrets.token_urlsafe(24)
    action.confirmation_token_hash = hashlib.sha256(token.encode()).hexdigest()
    action.confirmation_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.commit()
    return {**serialize_action(action), "confirmation_token": token}


@router.post("/actions/{action_id}/undo")
def undo(action_id: str, user: User = Depends(require_permissions("ai.actions")), db: Session = Depends(get_db)):
    result = undo_action(db, user, _action(db, user, action_id))
    db.commit()
    return result


@router.post("/messages/{message_id}/feedback")
def feedback(message_id: str, body: FeedbackBody, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    message = db.get(ChatMessage, message_id)
    if not message or message.organization_id != user.organization_id or message.role != "assistant":
        raise HTTPException(404, "Message not found")
    _conversation(db, user, message.conversation_id)
    row = db.execute(select(AIMessageFeedback).where(
        AIMessageFeedback.message_id == message.id, AIMessageFeedback.user_id == user.id,
    )).scalar_one_or_none()
    if row:
        row.rating, row.reason = body.rating, body.reason
    else:
        db.add(AIMessageFeedback(organization_id=user.organization_id,
                                 message_id=message.id, user_id=user.id, **body.model_dump()))
    db.commit()
    return {"ok": True, "message_id": message.id, **body.model_dump()}


@router.get("/usage")
def usage(user: User = Depends(require_permissions("billing.view")), db: Session = Depends(get_db)):
    month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = db.execute(select(
        AIUsage.route, func.sum(AIUsage.input_tokens), func.sum(AIUsage.output_tokens),
        func.sum(AIUsage.tool_calls), func.sum(AIUsage.credits_used),
    ).where(AIUsage.organization_id == user.organization_id,
            AIUsage.created_at >= month).group_by(AIUsage.route)).all()
    return [{"category": row[0], "input_tokens": row[1] or 0,
             "output_tokens": row[2] or 0, "operations": row[3] or 0,
             "credits_used": row[4] or 0} for row in rows]


@router.delete("/conversations/{cid}")
def delete_conversation(cid: str, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    row = _conversation(db, user, cid)
    if db.scalar(select(func.count(ChatTurn.id)).where(
        ChatTurn.conversation_id == row.id, ChatTurn.status == "processing",
    )):
        raise HTTPException(409, "Wait for the current answer to finish before deleting this chat")
    log_action(db, organization_id=user.organization_id, user_id=user.id,
               action="ai.conversation.delete", resource_type="conversation",
               resource_id=row.id, meta={"content_retained": False})
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.delete("/conversations/{cid}/turns/{turn_id}")
def delete_turn(cid: str, turn_id: str, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    conversation = _conversation(db, user, cid)
    turn = db.get(ChatTurn, turn_id)
    if not turn or turn.conversation_id != conversation.id or turn.organization_id != user.organization_id or turn.user_id != user.id:
        raise HTTPException(404, "Conversation turn not found")
    if turn.status == "processing":
        raise HTTPException(409, "Wait for this answer to finish before deleting it")
    db.delete(turn)
    conversation.state = {}
    log_action(db, organization_id=user.organization_id, user_id=user.id,
               action="ai.turn.delete", resource_type="conversation_turn", resource_id=turn_id,
               meta={"conversation_id": conversation.id, "content_retained": False})
    db.commit()
    db.refresh(conversation)
    return {"ok": True, "conversation_id": conversation.id, "turn_id": turn_id,
            "conversation": _conversation_summary(db, conversation)}
