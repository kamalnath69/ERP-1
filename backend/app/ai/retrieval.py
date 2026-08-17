"""Permission-scoped hybrid document retrieval."""
import hashlib
import logging
import re
from collections import defaultdict

from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import Session

from app.ai.provider import provider
from app.ai.v3_cache import QUERY_EMBEDDING_CACHE
from app.core.config import settings
from app.models import CollegeStudentProfile, Document, DocumentChunk, Organization, User
from app.services.access_policy import resolve_policy_context
from app.services.business_access import allowed_client_ids, allowed_location_ids
from app.services.college_access import resolve_college_access
from app.services.rbac import user_has_permissions


logger = logging.getLogger("edvatiq.ai.retrieval")


def document_access_conditions(db: Session, user: User):
    conditions = [Document.organization_id == user.organization_id]
    organization = db.get(Organization, user.organization_id)
    is_college = organization and organization.industry.value == "college"
    locations = allowed_location_ids(db, user)
    if locations is not None:
        conditions.append(or_(Document.location_id.is_(None), Document.location_id.in_(locations)))

    visibility = [
        Document.visibility == "team",
        (Document.visibility == "author_only") & (Document.uploaded_by_user_id == user.id),
        (Document.visibility == "managers") & (Document.uploaded_by_user_id == user.id),
    ]
    if user_has_permissions(db, user, ["documents.manage"]):
        visibility.append(Document.visibility == "managers")
    if user_has_permissions(db, user, ["clinical.view"]):
        visibility.append(Document.visibility == "clinical")
    conditions.append(or_(*visibility))

    if is_college:
        context = resolve_policy_context(db, user)
        access = resolve_college_access(db, user, "documents")
        student_docs = Document.entity_type.in_(["client", "patient", "student", "college_student"])
        offering_docs = Document.entity_type == "course_offering"
        if not context.has_sensitive("college.documents.sensitive.view"):
            conditions.append(~student_docs)
        elif not access.unrestricted:
            client_ids = set(db.execute(select(CollegeStudentProfile.client_id).where(
                CollegeStudentProfile.organization_id == user.organization_id,
                CollegeStudentProfile.id.in_(access.student_ids),
            )).scalars()) if access.student_ids else set()
            authorized_ids = client_ids | set(access.student_ids)
            conditions.append(or_(~student_docs, Document.entity_id.in_(authorized_ids) if authorized_ids else false()))
        if not access.unrestricted:
            conditions.append(or_(
                ~offering_docs,
                Document.entity_id.in_(access.course_offering_ids) if access.course_offering_ids else false(),
            ))
    else:
        clients = allowed_client_ids(db, user)
        if clients is not None:
            client_docs = Document.entity_type.in_(["client", "patient"])
            conditions.append(or_(~client_docs, Document.entity_id.in_(clients) if clients else false()))
    return conditions


def ensure_college_document_entity_access(db: Session, user: User, entity_type: str | None, entity_id: str | None) -> None:
    organization = db.get(Organization, user.organization_id)
    if not organization or organization.industry.value != "college":
        return
    context = resolve_policy_context(db, user)
    access = resolve_college_access(db, user, "documents")
    if entity_type in {"client", "patient", "student", "college_student"}:
        if not context.has_sensitive("college.documents.sensitive.view"):
            from fastapi import HTTPException
            raise HTTPException(403, "Sensitive student document access is required")
        student = db.execute(select(CollegeStudentProfile).where(
            CollegeStudentProfile.organization_id == user.organization_id,
            or_(CollegeStudentProfile.id == entity_id, CollegeStudentProfile.client_id == entity_id),
        )).scalar_one_or_none()
        if not student or not access.allows_student(student.id):
            from fastapi import HTTPException
            raise HTTPException(404, "Student not found")
    if entity_type == "course_offering" and not access.allows_course_offering(str(entity_id)):
        from fastapi import HTTPException
        raise HTTPException(404, "Course offering not found")


def retrieve(db: Session, user: User, query: str, limit: int = 8, document_id: str | None = None) -> dict:
    base = select(DocumentChunk, Document).join(Document, Document.id == DocumentChunk.document_id).where(
        Document.status == "ready", *document_access_conditions(db, user)
    )
    if document_id: base = base.where(Document.id == document_id)
    ranked: dict[str, float] = defaultdict(float)
    semantic_ids: set[str] = set()
    rows_by_id = {}
    provider_usage = {"embedding_tokens": 0, "provider_requests": 0}

    keyword = db.execute(
        base.where(DocumentChunk.search_vector.op("@@")(func.websearch_to_tsquery("simple", query)))
        .order_by(func.ts_rank_cd(DocumentChunk.search_vector, func.websearch_to_tsquery("simple", query)).desc())
        .limit(30)
    ).all()
    for rank, pair in enumerate(keyword, 1):
        ranked[pair[0].id] += 1 / (60 + rank)
        rows_by_id[pair[0].id] = pair

    client = provider()
    embedding_cache_status = "disabled"
    if client:
        try:
            normalized_query = " ".join(query.casefold().split())
            cache_key = (
                "retrieval-v3", settings.AI_EMBEDDING_MODEL, str(user.organization_id), str(user.id),
                int(user.access_version), hashlib.sha256(normalized_query.encode("utf-8")).hexdigest(),
            )
            cached_vector = QUERY_EMBEDDING_CACHE.get(cache_key)
            if cached_vector is None:
                embedding = client.embed([query])
                vector = embedding.vectors[0]
                QUERY_EMBEDDING_CACHE.set(cache_key, vector)
                embedding_cache_status = "miss"
                provider_usage = {
                    "embedding_tokens": embedding.input_tokens,
                    "provider_requests": embedding.provider_requests,
                }
            else:
                vector = cached_vector
                embedding_cache_status = "hit"
            distance = DocumentChunk.embedding_vector.cosine_distance(vector)
            with db.begin_nested():
                vector_rows = db.execute(
                    base.add_columns(distance.label("distance"))
                    .where(DocumentChunk.embedding_vector.is_not(None), distance <= 0.42)
                    .order_by(distance).limit(30)
                ).all()
            for rank, pair in enumerate(vector_rows, 1):
                ranked[pair[0].id] += 1 / (60 + rank)
                semantic_ids.add(pair[0].id)
                rows_by_id[pair[0].id] = pair[:2]
        except Exception as exc:
            logger.warning("embedding_search_unavailable error_type=%s", type(exc).__name__)

    if not ranked:
        fallback = db.execute(base.where(DocumentChunk.content.ilike(f"%{query}%")).limit(12)).all()
        for rank, pair in enumerate(fallback, 1):
            ranked[pair[0].id] = 1 / (60 + rank); rows_by_id[pair[0].id] = pair

    query_terms = set(re.findall(r"[\w]+", query.casefold()))

    def relevance(chunk_id: str) -> float:
        chunk, document = rows_by_id[chunk_id]
        candidate_terms = set(re.findall(r"[\w]+", f"{document.name} {chunk.section or ''} {chunk.content}".casefold()))
        overlap = len(query_terms & candidate_terms) / max(1, len(query_terms))
        phrase_bonus = 0.08 if query.casefold() in chunk.content.casefold() else 0
        semantic_bonus = 0.04 if chunk_id in semantic_ids else 0
        return ranked[chunk_id] + (overlap * 0.12) + phrase_bonus + semantic_bonus

    selected = []
    per_document = defaultdict(int)
    for chunk_id in sorted(ranked, key=relevance, reverse=True):
        if relevance(chunk_id) < 0.045:
            continue
        document_key = rows_by_id[chunk_id][1].id
        if per_document[document_key] >= 2:
            continue
        selected.append(chunk_id)
        per_document[document_key] += 1
        if len(selected) >= max(1, min(limit, 12)):
            break
    citations = []
    partial_index = False
    for chunk_id in selected:
        chunk, document = rows_by_id[chunk_id]
        partial_index = partial_index or bool((chunk.meta or {}).get("partial_index"))
        citations.append({
            "document_id": document.id, "document": document.name, "excerpt": chunk.content[:500],
            "page": chunk.page_number, "section": chunk.section,
            "href": f"/api/documents/{document.id}/download",
        })
    return {
        "query": query,
        "items": [{"content": item["excerpt"], **item} for item in citations],
        "citations": citations,
        "insufficient_evidence": not bool(citations),
        "missing_evidence": ["No document passage met the relevance threshold."] if not citations else [],
        "warnings": ["This document was only partially indexed because it exceeded the safe chunk limit."] if partial_index else [],
        "embedding_cache_status": embedding_cache_status,
        "_provider_usage": provider_usage,
    }
