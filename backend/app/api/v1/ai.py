"""Structured, streamed, metered AI business interface APIs."""
import asyncio
import base64
from contextlib import suppress
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import Field, field_validator
from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.orm import Session

from app.ai.actions import confirm_action as execute_confirmed_action, serialize_action, undo_action
from app.ai.contracts import compose_response
from app.ai.fast_queries import deterministic_query_plan, execute_deterministic_query
from app.ai.orchestrator import classify_route, fast_conversation_reply, run_ai_turn, selected_model
from app.ai.local_contracts import BusinessQueryV1, ResolvedEntity
from app.ai.local_executor import clarification_response, execute_local_query, run_local_result_page
from app.ai.local_intent import ENGINE_VERSION, interpret_business_query, normalize_language
from app.ai.personalization import load_assistant_preferences
from app.ai.tools import run_result_page
from app.core.database import SessionLocal, get_db
from app.schemas.validation import RequestModel
from app.core.deps import require_permissions
from app.models import (
    AIAction, AIIntentResolution, AIMessageFeedback, AIResultSession, AISavedView, AIUsage, AIWallet,
    ChatConversation, ChatMessage, ChatTurn, Client, CollegeCohort, CollegeDepartment, CollegeProgram,
    Document, FeatureFlag, Organization,
    PatientProfile, PlatformSetting, Setting, User,
)
from app.schemas import ChatMessageOut, ChatRequest, ConversationOut
from app.services.audit import log_action
from app.services.access_policy import policy_v2_enabled, resolve_policy_context
from app.services.business_access import ensure_client_access, ensure_location, tenant_get
from app.services.college_access import resolve_college_access
from app.services.rbac import user_has_permissions
from app.services.entity_resolution import validate_entity_ref
from app.services.realtime import publish_change
from app.services.ai_metering import calculate_charge, route_credit_limit
from app.services.wallet import release_reservation, reserve_credit_budget, settle_reservation, wallet_summary
from app.services.cursor_pagination import decode_cursor, encode_cursor, page_size

logger = logging.getLogger("edvatiq.ai")
router = APIRouter(prefix="/ai", tags=["ai"])


def require_ai_access(
    user: User = Depends(require_permissions("ai.use")),
    db: Session = Depends(get_db),
) -> User:
    organization = db.get(Organization, user.organization_id)
    if organization and organization.industry.value == "college" and policy_v2_enabled(db, user.organization_id):
        context = resolve_policy_context(db, user)
        if not context.active or "ai.use" not in context.permissions:
            raise HTTPException(403, "Edvatiq AI is not included in your active College access")
    return user


class ConfirmAction(RequestModel):
    confirmation_token: str | None = None


class SavedViewBody(RequestModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    query_spec: dict
    layout: list = []
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
    def validate_title(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("A chat title is required")
        value = " ".join(value.split())
        if not value:
            raise ValueError("A chat title is required")
        return value


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    scope: str = Query(default="active", pattern="^(active|archived|all)$"),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_ai_access),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    preview = select(ChatMessage.content).where(
        ChatMessage.conversation_id == ChatConversation.id, ChatMessage.role == "user",
    ).order_by(ChatMessage.created_at.desc()).limit(1).correlate(ChatConversation).scalar_subquery()
    turn_count = select(func.count(ChatTurn.id)).where(
        ChatTurn.conversation_id == ChatConversation.id,
    ).correlate(ChatConversation).scalar_subquery()
    active_stream = select(func.count(ChatTurn.id) > 0).where(
        ChatTurn.conversation_id == ChatConversation.id, ChatTurn.status == "processing",
    ).correlate(ChatConversation).scalar_subquery()
    stmt = select(ChatConversation, preview, turn_count, active_stream).where(
        ChatConversation.organization_id == user.organization_id, ChatConversation.user_id == user.id,
        or_(ChatConversation.expires_at.is_(None), ChatConversation.expires_at > now),
    )
    if scope == "active":
        stmt = stmt.where(ChatConversation.archived_at.is_(None))
    elif scope == "archived":
        stmt = stmt.where(ChatConversation.archived_at.is_not(None))
    search = (q or "").strip()
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        message_match = select(ChatMessage.id).where(
            ChatMessage.conversation_id == ChatConversation.id,
            ChatMessage.content.ilike(pattern, escape="\\"),
        ).exists()
        stmt = stmt.where(or_(
            ChatConversation.title.ilike(pattern, escape="\\"),
            message_match,
        ))
    rows = db.execute(stmt.order_by(
        ChatConversation.pinned_at.desc().nullslast(),
        ChatConversation.updated_at.desc(),
    ).limit(limit)).all()
    return [{"id": row.id, "title": row.title, "created_at": row.created_at, "updated_at": row.updated_at,
             "preview": message_preview, "turn_count": count, "active_stream": bool(is_active),
             "pinned_at": row.pinned_at, "archived_at": row.archived_at}
            for row, message_preview, count, is_active in rows]


@router.get("/conversations/page")
def conversation_page(
    scope: str = Query(default="active", pattern="^(active|archived|all)$"),
    q: str | None = Query(default=None, max_length=120),
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    user: User = Depends(require_ai_access),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    search = " ".join((q or "").split())
    filters = {"scope": scope, "q": search.casefold()}
    values = decode_cursor(cursor, scope="ai.conversations", organization_id=user.organization_id, filters=filters)
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
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        message_match = select(ChatMessage.id).where(
            ChatMessage.conversation_id == ChatConversation.id,
            ChatMessage.content.ilike(pattern, escape="\\"),
        ).exists()
        statement = statement.where(or_(
            ChatConversation.title.ilike(pattern, escape="\\"),
            message_match,
        ))
    pin_rank = case((ChatConversation.pinned_at.is_not(None), 1), else_=0)
    sort_at = func.coalesce(ChatConversation.pinned_at, ChatConversation.updated_at)
    if values:
        rank = int(values["rank"])
        pivot_at = datetime.fromisoformat(str(values["at"]))
        identifier = str(values["id"])
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
    items = [{
        "id": row.id,
        "title": row.title,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "preview": message_preview,
        "turn_count": count,
        "active_stream": bool(is_active),
        "pinned_at": row.pinned_at,
        "archived_at": row.archived_at,
    } for row, message_preview, count, is_active in rows]
    next_cursor = None
    if has_more and rows:
        last = rows[-1][0]
        next_cursor = encode_cursor(
            scope="ai.conversations",
            organization_id=user.organization_id,
            filters=filters,
            values={
                "rank": 1 if last.pinned_at else 0,
                "at": (last.pinned_at or last.updated_at).isoformat(),
                "id": last.id,
            },
        )
    return {"items": items, "next_cursor": next_cursor, "has_more": has_more}


@router.get("/conversations/{cid}", response_model=ConversationOut)
def get_conversation(cid: str, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    return _conversation_summary(db, _conversation(db, user, cid))


@router.get("/conversations/{cid}/messages", response_model=list[ChatMessageOut])
def get_messages(cid: str, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    conversation = _conversation(db, user, cid)
    rows = db.execute(select(ChatMessage).where(ChatMessage.conversation_id == conversation.id).order_by(ChatMessage.created_at)).scalars().all()
    ratings = dict(db.execute(select(AIMessageFeedback.message_id, AIMessageFeedback.rating).where(
        AIMessageFeedback.user_id == user.id,
        AIMessageFeedback.message_id.in_([row.id for row in rows]),
    )).all()) if rows else {}
    return [_authorized_message_dict(db, user, row, feedback_rating=ratings.get(row.id)) for row in rows]


@router.get("/conversations/{cid}/messages/page")
def message_page(
    cid: str,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_ai_access),
    db: Session = Depends(get_db),
):
    conversation = _conversation(db, user, cid)
    values = decode_cursor(
        cursor,
        scope=f"ai.messages:{conversation.id}",
        organization_id=user.organization_id,
    )
    statement = select(ChatMessage).where(ChatMessage.conversation_id == conversation.id)
    if values:
        pivot_at = datetime.fromisoformat(str(values["at"]))
        statement = statement.where(or_(
            ChatMessage.created_at < pivot_at,
            and_(ChatMessage.created_at == pivot_at, ChatMessage.id < str(values["id"])),
        ))
    size = page_size(limit, default=50)
    rows = list(db.execute(statement.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(size + 1)).scalars())
    has_more = len(rows) > size
    rows = rows[:size]
    oldest = rows[-1] if rows else None
    ratings = dict(db.execute(select(AIMessageFeedback.message_id, AIMessageFeedback.rating).where(
        AIMessageFeedback.user_id == user.id,
        AIMessageFeedback.message_id.in_([row.id for row in rows]),
    )).all()) if rows else {}
    next_cursor = encode_cursor(
        scope=f"ai.messages:{conversation.id}",
        organization_id=user.organization_id,
        values={"at": oldest.created_at.isoformat(), "id": oldest.id},
    ) if has_more and oldest else None
    return {
        "items": [_authorized_message_dict(db, user, row, feedback_rating=ratings.get(row.id)) for row in reversed(rows)],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@router.patch("/conversations/{cid}", response_model=ConversationOut)
def update_conversation(
    cid: str,
    body: ConversationUpdate,
    user: User = Depends(require_ai_access),
    db: Session = Depends(get_db),
):
    fields = body.model_fields_set & {"title", "pinned", "archived"}
    if not fields:
        raise HTTPException(422, "Choose a conversation change")
    if body.archived is True and body.pinned is True:
        raise HTTPException(422, "An archived chat cannot be pinned")
    conversation = _conversation(db, user, cid)
    processing = bool(db.scalar(select(func.count(ChatTurn.id)).where(
        ChatTurn.conversation_id == conversation.id,
        ChatTurn.status == "processing",
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
    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="ai.conversation.update",
        resource_type="conversation",
        resource_id=conversation.id,
        meta={"fields": sorted(fields)},
    )
    db.commit()
    db.refresh(conversation)
    return _conversation_summary(db, conversation)


def _conversation(db, user, conversation_id):
    row = db.get(ChatConversation, conversation_id)
    if not row or row.organization_id != user.organization_id or row.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    if row.expires_at and row.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(410, "This conversation has expired")
    return row


def _conversation_summary(db, conversation):
    preview = db.execute(select(ChatMessage.content).where(
        ChatMessage.conversation_id == conversation.id, ChatMessage.role == "user",
    ).order_by(ChatMessage.created_at.desc()).limit(1)).scalar_one_or_none()
    statuses = dict(db.execute(select(ChatTurn.status, func.count(ChatTurn.id)).where(
        ChatTurn.conversation_id == conversation.id,
    ).group_by(ChatTurn.status)).all())
    return {"id": conversation.id, "title": conversation.title, "created_at": conversation.created_at,
            "updated_at": conversation.updated_at, "preview": preview,
            "turn_count": sum(statuses.values()), "active_stream": bool(statuses.get("processing")),
            "pinned_at": conversation.pinned_at, "archived_at": conversation.archived_at}


def _context_identifier(value, label):
    if value is None or value == "":
        return None
    value = str(value).strip()
    if not value or len(value) > 80:
        raise HTTPException(422, f"{label} is invalid")
    return value


def _validated_college_scope(db, user, context):
    organization = db.get(Organization, user.organization_id)
    industry = getattr(getattr(organization, "industry", None), "value", getattr(organization, "industry", None))
    if industry != "college":
        raise HTTPException(404, "College scope not found")

    graduation_year = context.get("graduation_year")
    if graduation_year not in (None, ""):
        try:
            graduation_year = int(graduation_year)
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "Graduation year is invalid") from exc
        if graduation_year < 2000 or graduation_year > 2200:
            raise HTTPException(422, "Graduation year is invalid")
    else:
        graduation_year = None

    department_id = _context_identifier(context.get("department_id"), "Department")
    program_id = _context_identifier(context.get("program_id"), "Program")
    cohort_id = _context_identifier(context.get("cohort_id"), "Cohort")
    raw_cohort_ids = context.get("cohort_ids") or []
    if not isinstance(raw_cohort_ids, list) or len(raw_cohort_ids) > 50:
        raise HTTPException(422, "Cohort selection is invalid")
    cohort_ids = list(dict.fromkeys(
        _context_identifier(value, "Cohort") for value in raw_cohort_ids
    ))
    cohort_ids = [value for value in cohort_ids if value]
    if cohort_id and cohort_id not in cohort_ids:
        cohort_ids.append(cohort_id)
    if not any([graduation_year, department_id, program_id, cohort_ids]):
        raise HTTPException(422, "College context requires an academic scope")

    access = resolve_college_access(db, user, "students")
    statement = (
        select(CollegeCohort, CollegeProgram, CollegeDepartment)
        .join(CollegeProgram, CollegeProgram.id == CollegeCohort.program_id)
        .join(CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id)
        .where(
            CollegeCohort.organization_id == user.organization_id,
            CollegeProgram.organization_id == user.organization_id,
            CollegeDepartment.organization_id == user.organization_id,
            CollegeCohort.is_active.is_(True),
            CollegeProgram.is_active.is_(True),
            CollegeDepartment.is_active.is_(True),
        )
    )
    if graduation_year:
        statement = statement.where(CollegeCohort.graduation_year == graduation_year)
    if department_id:
        statement = statement.where(CollegeDepartment.id == department_id)
    if program_id:
        statement = statement.where(CollegeProgram.id == program_id)
    if cohort_ids:
        statement = statement.where(CollegeCohort.id.in_(cohort_ids))
    if not access.unrestricted:
        statement = statement.where(CollegeCohort.id.in_(set(access.cohort_ids)))

    rows = list(db.execute(statement.order_by(
        CollegeCohort.graduation_year,
        CollegeProgram.code,
        CollegeCohort.section,
        CollegeCohort.id,
    )).all())
    if not rows or (cohort_ids and {row[0].id for row in rows} != set(cohort_ids)):
        # Scope misses use 404 so callers cannot enumerate another user's College reach.
        raise HTTPException(404, "College scope not found")

    first_cohort, first_program, first_department = rows[0]
    if cohort_id and len(rows) == 1:
        display_name = f"{first_program.code} {first_cohort.graduation_year} / {first_cohort.section}"
        scope_id = f"cohort:{first_cohort.id}"
    elif program_id:
        display_name = first_program.name
        scope_id = f"program:{first_program.id}"
    elif department_id:
        display_name = first_department.name
        scope_id = f"department:{first_department.id}"
    elif graduation_year:
        display_name = f"{graduation_year} batch"
        scope_id = f"graduation:{graduation_year}"
    else:
        display_name = f"{len(rows)} selected cohorts"
        scope_id = f"cohorts:{len(rows)}"
    return {
        "kind": "college_scope",
        "id": scope_id,
        "display_name": display_name,
        "graduation_year": graduation_year,
        "department_id": department_id,
        "program_id": program_id,
        "cohort_id": cohort_id,
        "cohort_ids": cohort_ids,
    }


def _validated_context(db, user, context):
    if not context: return None
    kind, row_id = context.get("kind"), context.get("id")
    if not kind or not row_id: raise HTTPException(422, "Context requires kind and id")
    if kind == "college_scope":
        return _validated_college_scope(db, user, context)
    if kind == "document":
        from app.ai.retrieval import document_access_conditions
        document = db.execute(select(Document).where(Document.id == row_id, *document_access_conditions(db, user))).scalar_one_or_none()
        if not document: raise HTTPException(404, "Document not found")
        return {"kind": kind, "id": row_id}
    entity = validate_entity_ref(db, user, kind, row_id)
    if not entity: raise HTTPException(404, "Business record not found")
    return {"kind": entity["kind"], "id": entity["id"], "display_name": entity["display_name"]}


def _entity_ref(item):
    if not isinstance(item, dict): return None
    reference = item.get("profile_ref") or item.get("selection_ref")
    reference = reference or ({"kind": item.get("kind"), "id": item.get("id")} if item.get("kind") else None)
    if not reference or not reference.get("kind") or not reference.get("id"): return None
    result = {"kind": reference["kind"], "id": reference["id"]}
    for key in ["display_name", "display_meta"]:
        if item.get(key) is not None: result[key] = item[key]
    return result


def _turn_context(result, explicit=None):
    entities = []
    if explicit and explicit.get("kind") not in {"document", "college_scope"}: entities.append(_entity_ref(explicit))
    last_read = None
    for call in result.get("tool_calls", []):
        name, arguments, tool_result = call.get("name"), call.get("arguments") or {}, call.get("result") or {}
        if name in {"business_records", "business_analytics", "resolve_records", "entity_workspace", "client_workspace", "local_query"}:
            effective_arguments = tool_result.get("query_spec") if name in {"business_records", "local_query"} else None
            last_read = {"tool": name, "arguments": effective_arguments or arguments}
        if name == "entity_workspace":
            entities.append(_entity_ref({"kind": arguments.get("kind"), "id": arguments.get("id")}))
        selected = _entity_ref(tool_result.get("selected"))
        if selected: entities.append(selected)
        items = [] if name == "local_clarification" else (tool_result.get("items") or [])
        if len(items) <= 8: entities.extend(filter(None, (_entity_ref(item) for item in items)))
        client = tool_result.get("client")
        if name == "client_workspace" and isinstance(client, dict):
            entities.append(_entity_ref({"kind": "client", "id": client.get("id"),
                                         "display_name": client.get("display_name") or client.get("name")}))
    deduped = []
    for item in filter(None, entities):
        if not any(old["kind"] == item["kind"] and old["id"] == item["id"] for old in deduped): deduped.append(item)
    return deduped[:8], last_read


def _updated_context_state(previous, result, explicit=None):
    previous = dict(previous or {})
    entities, turn_read = _turn_context(result, explicit)
    last_read = turn_read or previous.get("last_read")
    existing = previous.get("recent_entities") or []
    combined = [item for item in entities + existing if item]
    deduped = []
    for item in combined:
        if not any(old.get("kind") == item.get("kind") and old.get("id") == item.get("id") for old in deduped):
            deduped.append(item)
    state = {"recent_entities": deduped[:8]}
    if entities:
        state["result_entities"] = entities[:8]
    elif previous.get("result_entities"):
        state["result_entities"] = previous["result_entities"][:8]
    unique_selected = next((_entity_ref((call.get("result") or {}).get("selected")) for call in result.get("tool_calls", []) if (call.get("result") or {}).get("resolution") == "unique"), None)
    workspace_selected = next((_entity_ref({"kind": (call.get("arguments") or {}).get("kind"),
                                             "id": (call.get("arguments") or {}).get("id")})
                               for call in result.get("tool_calls", []) if call.get("name") == "entity_workspace"), None)
    state["primary_entity"] = unique_selected or workspace_selected or (
        _entity_ref(explicit) if explicit and explicit.get("kind") not in {"document", "college_scope"} else previous.get("primary_entity")
    )
    college_scope = explicit if explicit and explicit.get("kind") == "college_scope" else previous.get("college_scope")
    if college_scope:
        state["college_scope"] = college_scope
    if last_read: state["last_read"] = last_read
    arguments = (last_read or {}).get("arguments") or {}
    filters = {key: value for key, value in arguments.items() if key not in {"location_id", "days"} and value is not None}
    if filters: state["filters"] = filters
    if arguments.get("days"): state["date_range"] = {"days": arguments["days"]}
    if arguments.get("location_id") or previous.get("location_id"):
        state["location_id"] = arguments.get("location_id") or previous.get("location_id")
    if previous.get("local_query"):
        state["local_query"] = previous["local_query"]
    return state


def _revalidated_context_state(db, user, state):
    state = state or {}; valid = []
    for item in state.get("recent_entities", [])[:8]:
        checked = validate_entity_ref(db, user, item.get("kind"), item.get("id")) if item.get("kind") and item.get("id") else None
        if checked: valid.append(_entity_ref(checked))
    primary = state.get("primary_entity") or {}
    checked_primary = validate_entity_ref(db, user, primary.get("kind"), primary.get("id")) if primary.get("kind") and primary.get("id") else None
    result = {"recent_entities": valid}
    valid_results = []
    for item in state.get("result_entities", [])[:8]:
        checked = validate_entity_ref(db, user, item.get("kind"), item.get("id")) if item.get("kind") and item.get("id") else None
        if checked:
            valid_results.append(_entity_ref(checked))
    if valid_results:
        result["result_entities"] = valid_results
    if checked_primary: result["primary_entity"] = _entity_ref(checked_primary)
    if state.get("last_read"): result["last_read"] = state["last_read"]
    for key in ["filters", "date_range"]:
        if state.get(key): result[key] = state[key]
    if state.get("college_scope"):
        try:
            result["college_scope"] = _validated_college_scope(db, user, state["college_scope"])
        except HTTPException:
            result.pop("last_read", None)
    if state.get("location_id"):
        try:
            ensure_location(db, user, state["location_id"])
            result["location_id"] = state["location_id"]
        except HTTPException:
            result.pop("last_read", None)
    if state.get("local_query"):
        try:
            query = BusinessQueryV1.model_validate(state["local_query"])
            if query.location_id:
                ensure_location(db, user, query.location_id)
            valid_query = all(
                validate_entity_ref(db, user, entity.kind, entity.id)
                for entity in query.entities
            )
            if valid_query:
                result["local_query"] = query.model_dump(mode="json")
        except (ValueError, HTTPException):
            pass
    return result


def _wallet_payload(db: Session, organization_id: str) -> dict | None:
    wallet = db.execute(select(AIWallet).where(AIWallet.organization_id == organization_id)).scalar_one_or_none()
    return wallet_summary(wallet) if wallet else None


def _local_intent_mode(db: Session, organization_id: str) -> str:
    flag = db.execute(select(FeatureFlag).where(
        FeatureFlag.organization_id == organization_id,
        FeatureFlag.flag == "ai.local_intent_v2",
    )).scalar_one_or_none()
    if not flag or not flag.enabled:
        return "disabled"
    mode = str((flag.meta or {}).get("mode", "enabled"))
    return mode if mode in {"enabled", "shadow"} else "enabled"


def _record_intent_resolution(db, user, conversation_id, message, match, outcome, latency_ms):
    normalized, _ = normalize_language(message)
    query = match.query
    db.add(AIIntentResolution(
        organization_id=user.organization_id, user_id=user.id, conversation_id=conversation_id,
        request_hash=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        engine_version=ENGINE_VERSION, intent=query.intent if query else None,
        subject=query.subject if query else None, confidence=match.confidence,
        outcome=outcome, latency_ms=latency_ms,
        meta={"reason": match.reason, "ambiguous": match.outcome == "clarify"},
    ))


async def _process_chat(body, user, db, emit=None):
    assistant_preferences = load_assistant_preferences(db, user)
    fast_reply = fast_conversation_reply(body.message, assistant_preferences)
    deterministic_plan = None
    context = _validated_context(db, user, body.context)
    if body.location_id: ensure_location(db, user, body.location_id)
    local_match = None
    local_outcome = "disabled"
    organization = db.get(Organization, user.organization_id)
    industry = getattr(organization.industry, "value", organization.industry) if organization else None
    is_college = industry == "college"
    college_policy_enabled = bool(is_college and policy_v2_enabled(db, user.organization_id))
    initial_access_version = user.access_version
    initial_policy_version = None
    verified_policy_context = None
    original_emit = emit
    buffered_text_events: list[tuple[str, dict]] = []
    if college_policy_enabled:
        initial_policy_context = resolve_policy_context(db, user)
        if not initial_policy_context.active or "ai.use" not in initial_policy_context.permissions:
            raise HTTPException(403, "Edvatiq AI is not included in your active College access")
        initial_policy_version = initial_policy_context.policy_version
        if original_emit:
            async def policy_guarded_emit(name, payload):
                if name == "text_delta":
                    buffered_text_events.append((name, payload))
                    return
                await original_emit(name, payload)

            emit = policy_guarded_emit
    route = "conversation" if fast_reply else "college" if is_college else classify_route(body.message, context)
    key = body.idempotency_key or f"ai:{user.id}:{secrets.token_urlsafe(16)}"
    lock_key = f"ai-turn:{user.organization_id}:{user.id}:{key}"
    db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(lock_key, 0))))
    existing_turn = db.execute(select(ChatTurn).where(
        ChatTurn.organization_id == user.organization_id, ChatTurn.user_id == user.id, ChatTurn.request_key == key,
    )).scalar_one_or_none()
    if existing_turn and existing_turn.status == "completed":
        existing = db.execute(select(ChatMessage).where(ChatMessage.turn_id == existing_turn.id, ChatMessage.role == "assistant")).scalar_one_or_none()
        if existing:
            conversation = _conversation(db, user, existing.conversation_id)
            return {"conversation_id": existing.conversation_id, "conversation": _conversation_summary(db, conversation),
                    "message": _authorized_message_dict(db, user, existing), "credits_used": 0,
                    "ai_wallet": _wallet_payload(db, user.organization_id)}
    if existing_turn and existing_turn.status == "processing": raise HTTPException(409, "This request is already being processed")
    reservation = None; turn = existing_turn
    conversation = None
    if turn:
        conversation = _conversation(db, user, turn.conversation_id)
    elif body.conversation_id:
        conversation = _conversation(db, user, body.conversation_id)
    if conversation and conversation.archived_at:
        raise HTTPException(409, "Restore this chat before continuing it")
    try:
        if turn:
            db.execute(delete(ChatMessage).where(ChatMessage.turn_id == turn.id))
            turn.status = "processing"; turn.error_code = None; turn.completed_at = None
        elif not conversation:
            retention = db.execute(select(Setting).where(Setting.organization_id == user.organization_id,
                                   Setting.key == "ai.conversation_retention_days")).scalar_one_or_none()
            retention_days = max(1, min(int((retention.value or {}).get("days", 90)), 3650)) if retention else 90
            conversation = ChatConversation(
                organization_id=user.organization_id, user_id=user.id, title=body.message[:60],
                provider="local" if fast_reply else "openai",
                model="instant" if fast_reply else selected_model(db, user, route),
                expires_at=datetime.now(timezone.utc) + timedelta(days=retention_days),
            )
            db.add(conversation); db.flush()
        conversation.context_state = _revalidated_context_state(db, user, conversation.context_state)
        if body.location_id:
            conversation.context_state = {**conversation.context_state, "location_id": body.location_id}
        mode = _local_intent_mode(db, user.organization_id)
        if not fast_reply and mode != "disabled" and not is_college:
            intent_started = perf_counter()
            local_match = interpret_business_query(
                db, user, body.message,
                body.location_id or conversation.context_state.get("location_id"),
                conversation.context_state,
            )
            if local_match.query and context and not local_match.query.entities:
                client_subjects = {"appointments", "invoices", "memberships", "checkins", "class_bookings", "measurements", "goals", "workouts", "diets", "coaching", "signals", "commitments", "memories", "salon_profiles"}
                clinical_subjects = {"encounters", "vitals", "allergies", "diagnoses", "prescriptions", "lab_orders", "lab_results", "dispenses"}
                context_kind = context.get("kind")
                if (context_kind == "client" and local_match.query.subject in client_subjects) or (
                    context_kind == "catalog" and local_match.query.subject == "purchases"
                ):
                    local_match.query.entities.append(ResolvedEntity(
                        kind=context_kind, id=context["id"],
                        display_name=context.get("display_name") or "Business record",
                        confidence=1.0, profile_ref={"kind": context_kind, "id": context["id"]},
                    ))
                elif context_kind == "patient" and local_match.query.subject in clinical_subjects:
                    local_match.query.entities.append(ResolvedEntity(
                        kind="patient", id=context["id"],
                        display_name=context.get("display_name") or "Patient", confidence=1.0,
                        profile_ref=None,
                    ))
                elif context_kind == "client" and local_match.query.subject in clinical_subjects and user_has_permissions(db, user, ["clinical.view"]):
                    patient = db.execute(select(PatientProfile).where(
                        PatientProfile.organization_id == user.organization_id,
                        PatientProfile.client_id == context["id"],
                    )).scalar_one_or_none()
                    if patient:
                        local_match.query.entities.append(ResolvedEntity(
                            kind="patient", id=patient.id,
                            display_name=context.get("display_name") or "Patient", confidence=1.0,
                            profile_ref={"kind": "client", "id": context["id"]},
                        ))
            local_outcome = "shadow" if mode == "shadow" else local_match.outcome
            _record_intent_resolution(
                db, user, conversation.id, body.message, local_match, local_outcome,
                int((perf_counter() - intent_started) * 1000),
            )
        if not fast_reply and not (
            local_match and local_outcome in {"local", "clarify"}
        ):
            candidate_plan = deterministic_query_plan(
                body.message,
                body.location_id or conversation.context_state.get("location_id"),
                conversation.context_state,
            )
            if is_college:
                arguments = (candidate_plan or {}).get("arguments") or {}
                has_college_scope = bool(
                    (context or {}).get("kind") == "college_scope"
                    or conversation.context_state.get("college_scope")
                )
                deterministic_plan = candidate_plan if (
                    not has_college_scope
                    and candidate_plan
                    and candidate_plan.get("tool") == "business_records"
                    and arguments.get("subject") == "students"
                    and set(arguments).issubset({"subject", "location_id", "status"})
                ) else None
            else:
                deterministic_plan = candidate_plan
        free_path = bool(fast_reply or (
            local_match and local_outcome in {"local", "clarify"}
        ) or deterministic_plan)
        if free_path:
            conversation.provider = "local"
            conversation.model = "instant" if fast_reply else "database"
        if not turn:
            turn = ChatTurn(organization_id=user.organization_id, conversation_id=conversation.id,
                            user_id=user.id, request_key=key, status="processing")
            db.add(turn); db.flush()
        if not free_path:
            organization = db.get(Organization, user.organization_id)
            reservation = reserve_credit_budget(db, organization, route_credit_limit(db, route), key)
        user_message = ChatMessage(
            organization_id=user.organization_id, conversation_id=conversation.id, turn_id=turn.id, role="user", content=body.message,
            meta={"idempotency_key": key, "context": context, "location_id": body.location_id},
        )
        conversation.updated_at = datetime.now(timezone.utc)
        db.add(user_message)
        if free_path:
            db.flush()
        else:
            db.commit()
        if fast_reply:
            if emit:
                await emit("status", {"message": "Ready"})
                await emit("text_delta", {"text": fast_reply["content"]})
            structured_fast = compose_response(fast_reply["content"], []).model_dump(mode="json")
            result = {
                "content": fast_reply["content"], "tool_calls": [], "model": "instant", "route": route,
                "response": structured_fast,
                "usage": {"input_tokens": 0, "output_tokens": 0, "tool_calls": 0, "tool_latency_ms": 0, "latency_ms": 0},
            }
        elif local_match and local_outcome == "local" and local_match.query:
            if emit:
                await emit("status", {"message": "Checking current business information"})
            result = execute_local_query(
                db, user, local_match.query, conversation.id, assistant_preferences,
            )
            if emit:
                await emit("text_delta", {"text": result["content"]})
        elif local_match and local_outcome == "clarify" and local_match.clarification:
            if emit:
                await emit("status", {"message": "I found a few possible matches"})
            result = clarification_response(local_match.clarification)
            if emit:
                await emit("text_delta", {"text": result["content"]})
        elif deterministic_plan:
            if emit:
                await emit("status", {"message": "Checking current business information"})
            result = execute_deterministic_query(
                db, user, conversation.id, deterministic_plan, assistant_preferences,
            )
            if emit:
                await emit("text_delta", {"text": result["content"]})
        else:
            if emit:
                await emit("status", {"message": "Reviewing this conversation"})
            recent_history = db.execute(select(ChatMessage).where(
                ChatMessage.conversation_id == conversation.id,
            ).order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(60)).scalars().all()
            history = list(reversed(recent_history))
            result = await run_ai_turn(
                db,
                user,
                conversation,
                history,
                body.location_id,
                context,
                emit=emit,
                preferences=assistant_preferences,
            )
        if college_policy_enabled:
            current_access_version = db.execute(
                select(User.access_version).where(User.id == user.id).with_for_update()
            ).scalar_one()
            db.refresh(user)
            verified_policy_context = resolve_policy_context(db, user)
            if (
                current_access_version != initial_access_version
                or not verified_policy_context.active
                or "ai.use" not in verified_policy_context.permissions
                or verified_policy_context.policy_version != initial_policy_version
            ):
                raise HTTPException(
                    409,
                    "Your access changed while this answer was being prepared. Ask again for a current answer.",
                )
        structured = result["response"]
        usage = result.get("usage") or {}
        charge = calculate_charge(db, result.get("model", "configured"), usage)
        stored_blocks = _without_confirmation_tokens(structured.get("blocks", []))
        assistant = ChatMessage(
            organization_id=user.organization_id, conversation_id=conversation.id, turn_id=turn.id, role="assistant",
            content=structured["summary"], tool_calls=_without_confirmation_tokens(result.get("tool_calls") or None),
            blocks=stored_blocks, citations=structured.get("citations", []),
            response_schema_version=structured.get("schema_version", 1),
            meta={"route": result.get("route"), "request_key": key, "result_session_id": structured.get("result_session_id")},
        )
        db.add(assistant)
        turn_entities, turn_read = _turn_context(result, context)
        conversation.context_state = _updated_context_state(conversation.context_state, result, context)
        if local_match and local_outcome == "local" and local_match.query:
            conversation.context_state["local_query"] = local_match.query.model_dump(mode="json")
        assistant.meta = {**assistant.meta, "resolved_entities": conversation.context_state.get("recent_entities", []),
                          "last_read": conversation.context_state.get("last_read"),
                          "turn_entities": turn_entities, "turn_read": turn_read,
                          "result_entities": conversation.context_state.get("result_entities", []),
                          "local_query": conversation.context_state.get("local_query")}
        if college_policy_enabled:
            policy_context = verified_policy_context or resolve_policy_context(db, user)
            document_refs = [{"kind": "document", "id": item.get("document_id")} for item in (
                structured.get("citations") or []
            ) if item.get("document_id")]
            assistant.meta = {
                **assistant.meta,
                "policy_version": policy_context.policy_version,
                "access_version": policy_context.access_version,
                "evidence_refs": [*turn_entities, *document_refs],
            }
        turn.status = "completed"; turn.completed_at = datetime.now(timezone.utc); turn.error_code = None
        conversation.updated_at = datetime.now(timezone.utc)
        credits_used = 0
        settled_wallet = None
        if reservation:
            credits_used = min(charge.credits, reservation.credits)
            db.add(AIUsage(
                organization_id=user.organization_id, user_id=user.id, model=result.get("model", "configured"),
                input_tokens=int(usage.get("input_tokens", 0)),
                cached_input_tokens=int(usage.get("cached_input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
                embedding_tokens=int(usage.get("embedding_tokens", 0)),
                provider_requests=int(usage.get("provider_requests", 0)),
                tool_calls=int(usage.get("tool_calls", 0)), latency_ms=usage.get("latency_ms"),
                tool_latency_ms=int(usage.get("tool_latency_ms", 0)), route=result.get("route", route),
                status="completed", credits_used=credits_used,
                provider_cost_paise=charge.provider_cost_paise, rate_version=charge.rate_version,
            ))
            settled_wallet = settle_reservation(db, reservation, charge.credits)
        log_action(db, organization_id=user.organization_id, user_id=user.id, action="ai.chat",
                   resource_type="conversation", resource_id=conversation.id,
                   meta={"route": result.get("route"), "tools": [item["name"] for item in result.get("tool_calls", [])]})
        db.commit(); db.refresh(assistant)
        if original_emit and buffered_text_events:
            for event_name, event_payload in buffered_text_events:
                await original_emit(event_name, event_payload)
        if settled_wallet:
            try:
                await asyncio.to_thread(publish_change, str(user.organization_id), "/ai/wallet")
            except Exception as exc:
                logger.warning("ai_wallet_publish_failed organization=%s error_type=%s", user.organization_id, type(exc).__name__)
        return {"conversation_id": conversation.id, "conversation": _conversation_summary(db, conversation),
                "message": _message_dict(assistant, structured.get("actions", []), structured.get("blocks", [])),
                "credits_used": credits_used,
                "ai_wallet": wallet_summary(settled_wallet) if settled_wallet else _wallet_payload(db, user.organization_id)}
    except (Exception, asyncio.CancelledError) as exc:
        db.rollback()
        if reservation:
            reservation = db.get(type(reservation), reservation.id)
            if reservation:
                release_reservation(db, reservation)
        if turn and turn.id:
            failed_turn = db.get(ChatTurn, turn.id)
            if failed_turn:
                db.execute(delete(ChatMessage).where(ChatMessage.turn_id == failed_turn.id))
                failed_turn.status = "cancelled" if isinstance(exc, asyncio.CancelledError) else "failed"
                failed_turn.error_code = "cancelled" if isinstance(exc, asyncio.CancelledError) else type(exc).__name__[:80]
        db.commit()
        raise


def _without_confirmation_tokens(value):
    if isinstance(value, list): return [_without_confirmation_tokens(item) for item in value]
    if isinstance(value, dict): return {key: _without_confirmation_tokens(item) for key, item in value.items() if key != "confirmation_token"}
    return value


def _message_dict(message, actions=None, blocks=None, feedback_rating=None):
    return {"id": message.id, "conversation_id": message.conversation_id, "turn_id": message.turn_id, "role": message.role, "content": message.content, "blocks": blocks if blocks is not None else _decorate_blocks(message),
            "citations": message.citations, "actions": actions or [], "created_at": message.created_at,
            "response_schema_version": message.response_schema_version,
            "feedback_rating": feedback_rating}


def _authorized_message_dict(db: Session, user: User, message: ChatMessage, **kwargs) -> dict:
    result = _message_dict(message, **kwargs)
    if message.role != "assistant":
        return result
    organization = db.get(Organization, user.organization_id)
    if not organization or organization.industry.value != "college" or not policy_v2_enabled(db, user.organization_id):
        return result
    context = resolve_policy_context(db, user)
    if not context.active or "ai.use" not in context.permissions:
        authorized = False
    else:
        meta = message.meta or {}
        stored_access_version = meta.get("access_version")
        if stored_access_version == user.access_version:
            authorized = True
        else:
            references = meta.get("evidence_refs") or meta.get("turn_entities") or []
            authorized = bool(references) or context.maximum_scope.unrestricted
            for reference in references:
                kind, identifier = reference.get("kind"), reference.get("id")
                if not kind or not identifier:
                    authorized = False
                    break
                try:
                    if kind == "document":
                        from app.ai.retrieval import document_access_conditions
                        visible = db.execute(select(Document.id).where(
                            Document.id == identifier, *document_access_conditions(db, user),
                        )).scalar_one_or_none()
                    else:
                        visible = validate_entity_ref(db, user, kind, identifier)
                except HTTPException:
                    visible = None
                if not visible:
                    authorized = False
                    break
    if authorized:
        return result
    return {
        **result,
        "content": "This answer is hidden because your data access changed. Ask again for a current, authorized answer.",
        "blocks": [],
        "citations": [],
        "actions": [],
    }


def _decorate_blocks(message: ChatMessage) -> list[dict]:
    blocks = [dict(block or {}) for block in (message.blocks or [])]
    meta = message.meta or {}
    preferred_query = meta.get("local_query")
    turn_read = meta.get("turn_read") or meta.get("last_read") or {}
    fallback_query = turn_read.get("arguments") if turn_read.get("tool") in {"business_records", "local_query"} else None
    query_spec = preferred_query or fallback_query
    if not query_spec:
        return blocks
    for block in blocks:
        if block.get("type") not in {"table", "entity_cards"}:
            continue
        data = dict(block.get("data") or {})
        if data.get("query_spec"):
            continue
        if data.get("result_session_id") or data.get("items"):
            data["query_spec"] = query_spec
            block["data"] = data
    return blocks


@router.post("/chat")
async def chat(body: ChatRequest, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    try: return await _process_chat(body, user, db)
    except HTTPException: raise
    except Exception:
        logger.exception("ai_chat_failed organization=%s user=%s", user.organization_id, user.id)
        raise HTTPException(502, "Edvatiq could not complete that request. Please try again.")


def _event(name, payload):
    return f"event: {name}\ndata: {json.dumps(payload, default=str)}\n\n"


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, user: User = Depends(require_ai_access)):
    # Request dependencies may be released before StreamingResponse starts iterating.
    # Keep only scalar identity here and give the producer its own session lifecycle.
    stream_user_id = user.id
    stream_organization_id = user.organization_id

    async def events():
        queue = asyncio.Queue()

        async def emit(name, payload):
            await queue.put((name, payload))

        async def produce():
            try:
                with SessionLocal() as stream_db:
                    stream_user = stream_db.get(User, stream_user_id)
                    if (
                        not stream_user
                        or not stream_user.is_active
                        or stream_user.organization_id != stream_organization_id
                    ):
                        raise HTTPException(401, "Authentication session is no longer active")
                    if not user_has_permissions(stream_db, stream_user, ["ai.use"]):
                        raise HTTPException(403, "Edvatiq AI access is no longer available")
                    result = await _process_chat(body, stream_user, stream_db, emit=emit)
                for block in result["message"].get("blocks", []):
                    if block.get("type") != "text":
                        await emit("block", block)
                for action in result["message"].get("actions", []):
                    await emit("action", action)
                await emit("complete", result)
            except Exception as exc:
                if not isinstance(exc, HTTPException):
                    logger.exception(
                        "ai_stream_failed organization=%s user=%s",
                        stream_organization_id,
                        stream_user_id,
                    )
                message = exc.detail if isinstance(exc, HTTPException) and isinstance(exc.detail, str) else "Edvatiq could not complete that request."
                await emit("error", {"message": message})
            finally:
                await queue.put(("done", None))

        producer = asyncio.create_task(produce())
        try:
            yield _event("accepted", {"request_id": body.idempotency_key})
            yield _event("status", {"message": "Understanding your request"})
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
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/results/{session_id}")
def result_page(session_id: str, cursor: str | None = None, limit: int = 25,
                user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    row = db.get(AIResultSession, session_id)
    if not row or row.organization_id != user.organization_id or row.user_id != user.id: raise HTTPException(404, "Result not found")
    if row.expires_at < datetime.now(timezone.utc): raise HTTPException(410, "This result has expired")
    return _run_query_page(db, user, row.query_spec, row.result_type, cursor, limit)


@router.post("/results/run")
def run_result_query(body: ResultQueryBody, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    _validate_query_spec(body.query_spec)
    result_type = body.query_spec.get("subject") or "results"
    return _run_query_page(db, user, body.query_spec, result_type, body.cursor, body.limit)


def _run_query_page(db: Session, user: User, query_spec: dict, result_type: str, cursor: str | None, limit: int):
    try: offset = int(base64.urlsafe_b64decode(cursor.encode()).decode()) if cursor else 0
    except Exception: raise HTTPException(422, "Invalid cursor")
    result = (
        run_local_result_page(db, user, query_spec, offset, limit)
        if query_spec.get("engine") == "local_v1"
        else run_result_page(db, user, query_spec, offset, limit)
    )
    next_offset = result.pop("next_offset", None)
    result["next_cursor"] = base64.urlsafe_b64encode(str(next_offset).encode()).decode() if next_offset is not None else None
    result["query_spec"] = query_spec
    result["result_type"] = result_type
    return result


@router.get("/views")
def list_views(user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    rows = db.execute(select(AISavedView).where(AISavedView.organization_id == user.organization_id,
                      AISavedView.is_active.is_(True), or_(AISavedView.owner_user_id == user.id, AISavedView.visibility == "team"))
                      .order_by(AISavedView.updated_at.desc())).scalars()
    return [_view_dict(row) for row in rows]


@router.post("/views", status_code=201)
def create_view(body: SavedViewBody, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    if body.visibility == "team":
        from app.models import Organization
        from app.services.entitlements import entitlement_value
        if not user_has_permissions(db, user, ["ai.views.share"]) or not entitlement_value(db, db.get(Organization, user.organization_id), "ai.views.share", False): raise HTTPException(403, "Team sharing is not included in your access and plan")
    _validate_query_spec(body.query_spec)
    row = AISavedView(organization_id=user.organization_id, owner_user_id=user.id, **body.model_dump(exclude={"version"}))
    db.add(row); db.commit(); db.refresh(row); return _view_dict(row)


@router.patch("/views/{view_id}")
def update_view(view_id: str, body: SavedViewBody, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    row = tenant_get(db, AISavedView, view_id, user)
    if row.owner_user_id != user.id: raise HTTPException(403, "Only the owner can edit this view")
    if body.version != row.version: raise HTTPException(409, "This view changed. Refresh and try again")
    if body.visibility == "team":
        from app.models import Organization
        from app.services.entitlements import entitlement_value
        if not user_has_permissions(db, user, ["ai.views.share"]) or not entitlement_value(db, db.get(Organization, user.organization_id), "ai.views.share", False): raise HTTPException(403, "Team sharing is not included in your access and plan")
    _validate_query_spec(body.query_spec)
    for key, value in body.model_dump(exclude={"version"}).items(): setattr(row, key, value)
    row.version += 1; db.commit(); return _view_dict(row)


@router.delete("/views/{view_id}")
def delete_view(view_id: str, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    row = tenant_get(db, AISavedView, view_id, user)
    if row.owner_user_id != user.id: raise HTTPException(403, "Only the owner can remove this view")
    row.is_active = False; row.version += 1; db.commit(); return {"ok": True}


@router.post("/views/{view_id}/run")
def run_view(view_id: str, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    row = tenant_get(db, AISavedView, view_id, user)
    if row.owner_user_id != user.id and row.visibility != "team": raise HTTPException(404, "View not found")
    result = run_local_result_page(db, user, row.query_spec, 0, 25) if row.query_spec.get("engine") == "local_v1" else run_result_page(db, user, row.query_spec, 0, 25)
    return {"view": _view_dict(row), "result": result}


def _validate_query_spec(spec):
    if spec.get("engine") == "local_v1":
        try:
            BusinessQueryV1.model_validate(spec)
            return
        except ValueError:
            raise HTTPException(422, "Unsupported saved query")
    if spec.get("subject") not in {"clients", "employees", "appointments", "sales", "purchases", "catalog", "inventory", "memberships", "checkins", "clinic_queue", "patients"}:
        raise HTTPException(422, "Unsupported saved query")


def _view_dict(row):
    return {key: getattr(row, key) for key in ["id", "name", "description", "query_spec", "layout", "visibility", "version", "owner_user_id", "updated_at"]}


@router.get("/actions")
def list_actions(user: User = Depends(require_permissions("ai.actions")), db: Session = Depends(get_db)):
    rows = db.execute(select(AIAction).where(AIAction.organization_id == user.organization_id, AIAction.user_id == user.id).order_by(AIAction.created_at.desc()).limit(100)).scalars()
    return [serialize_action(row) for row in rows]


@router.post("/actions/{action_id}/confirm")
def confirm(action_id: str, body: ConfirmAction, user: User = Depends(require_permissions("ai.actions")), db: Session = Depends(get_db)):
    action = tenant_get(db, AIAction, action_id, user)
    result = execute_confirmed_action(db, user, action, body.confirmation_token); db.commit(); return result


@router.post("/actions/{action_id}/confirmation")
def renew_confirmation(action_id: str, user: User = Depends(require_permissions("ai.actions")), db: Session = Depends(get_db)):
    action = tenant_get(db, AIAction, action_id, user)
    if action.user_id != user.id or action.status != "pending_confirmation": raise HTTPException(409, "This action is not waiting for confirmation")
    if not action.required_permission or not user_has_permissions(db, user, [action.required_permission]): raise HTTPException(403, "Access denied")
    token = secrets.token_urlsafe(24)
    action.confirmation_token_hash = hashlib.sha256(token.encode()).hexdigest()
    action.confirmation_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.commit(); return {**serialize_action(action), "confirmation_token": token}


@router.post("/actions/{action_id}/undo")
def undo(action_id: str, user: User = Depends(require_permissions("ai.actions")), db: Session = Depends(get_db)):
    action = tenant_get(db, AIAction, action_id, user)
    result = undo_action(db, user, action); db.commit(); return result


@router.post("/messages/{message_id}/feedback")
def feedback(message_id: str, body: FeedbackBody, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    message = db.get(ChatMessage, message_id)
    if not message or message.organization_id != user.organization_id or message.role != "assistant": raise HTTPException(404, "Message not found")
    _conversation(db, user, message.conversation_id)
    row = db.execute(select(AIMessageFeedback).where(AIMessageFeedback.message_id == message.id, AIMessageFeedback.user_id == user.id)).scalar_one_or_none()
    if row: row.rating = body.rating; row.reason = body.reason
    else: db.add(AIMessageFeedback(organization_id=user.organization_id, message_id=message.id, user_id=user.id, **body.model_dump()))
    intent = db.execute(select(AIIntentResolution).where(
        AIIntentResolution.organization_id == user.organization_id,
        AIIntentResolution.user_id == user.id,
        AIIntentResolution.conversation_id == message.conversation_id,
        AIIntentResolution.created_at <= message.created_at,
    ).order_by(AIIntentResolution.created_at.desc()).limit(1)).scalar_one_or_none()
    if intent:
        intent.meta = {**(intent.meta or {}), "correction_outcome": body.rating}
    db.commit(); return {"ok": True, "message_id": message.id, "rating": body.rating, "reason": body.reason}


@router.get("/usage")
def usage(user: User = Depends(require_permissions("billing.view")), db: Session = Depends(get_db)):
    month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = db.execute(select(AIUsage.route, func.sum(AIUsage.input_tokens), func.sum(AIUsage.output_tokens), func.sum(AIUsage.tool_calls), func.sum(AIUsage.credits_used)).where(AIUsage.organization_id == user.organization_id, AIUsage.created_at >= month).group_by(AIUsage.route)).all()
    return [{"category": row[0], "input_tokens": row[1] or 0, "output_tokens": row[2] or 0, "operations": row[3] or 0, "credits_used": row[4] or 0} for row in rows]


@router.delete("/conversations/{cid}")
def delete_conversation(cid: str, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    row = _conversation(db, user, cid)
    if db.scalar(select(func.count(ChatTurn.id)).where(ChatTurn.conversation_id == row.id, ChatTurn.status == "processing")):
        raise HTTPException(409, "Wait for the current answer to finish before deleting this chat")
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="ai.conversation.delete",
               resource_type="conversation", resource_id=row.id, meta={"content_retained": False})
    db.delete(row); db.commit(); return {"ok": True}


def _rebuild_conversation_context(db, conversation):
    recent = []; last_read = None; local_query = None; result_entities = None
    messages = db.execute(select(ChatMessage).where(
        ChatMessage.conversation_id == conversation.id, ChatMessage.role == "assistant",
    ).order_by(ChatMessage.created_at.desc()).limit(20)).scalars().all()
    for message in messages:
        meta = message.meta or {}
        if not last_read and (meta.get("turn_read") or meta.get("last_read")):
            last_read = meta.get("turn_read") or meta.get("last_read")
        if not local_query and meta.get("local_query"):
            local_query = meta["local_query"]
        if result_entities is None and meta.get("result_entities"):
            result_entities = meta["result_entities"]
        # New turns store only the references introduced by that turn. Legacy
        # messages fall back to their historical accumulated context.
        introduced = meta["turn_entities"] if "turn_entities" in meta else meta.get("resolved_entities", [])
        for item in introduced:
            if item and not any(old.get("kind") == item.get("kind") and old.get("id") == item.get("id") for old in recent):
                recent.append(item)
    conversation.context_state = {"recent_entities": recent[:8]}
    if recent: conversation.context_state["primary_entity"] = recent[0]
    if result_entities:
        conversation.context_state["result_entities"] = result_entities[:8]
    if last_read:
        conversation.context_state["last_read"] = last_read
        arguments = last_read.get("arguments") or {}
        filters = {key: value for key, value in arguments.items() if key not in {"location_id", "days"} and value is not None}
        if filters: conversation.context_state["filters"] = filters
        if arguments.get("days"): conversation.context_state["date_range"] = {"days": arguments["days"]}
        if arguments.get("location_id"): conversation.context_state["location_id"] = arguments["location_id"]
    if local_query:
        conversation.context_state["local_query"] = local_query


@router.delete("/conversations/{cid}/turns/{turn_id}")
def delete_turn(cid: str, turn_id: str, user: User = Depends(require_ai_access), db: Session = Depends(get_db)):
    conversation = _conversation(db, user, cid)
    turn = db.get(ChatTurn, turn_id)
    if not turn or turn.conversation_id != conversation.id or turn.organization_id != user.organization_id or turn.user_id != user.id:
        raise HTTPException(404, "Conversation turn not found")
    if turn.status == "processing": raise HTTPException(409, "Wait for this answer to finish before deleting it")
    db.delete(turn); db.flush(); _rebuild_conversation_context(db, conversation)
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="ai.turn.delete",
               resource_type="conversation_turn", resource_id=turn_id,
               meta={"conversation_id": conversation.id, "content_retained": False, "business_actions_reversed": False})
    db.commit(); db.refresh(conversation)
    return {"ok": True, "conversation_id": conversation.id, "turn_id": turn_id,
            "conversation": _conversation_summary(db, conversation)}
