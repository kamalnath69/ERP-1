"""Permission-scoped hybrid document retrieval."""
import logging
from collections import defaultdict

from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import Session

from app.ai.provider import provider
from app.models import Document, DocumentChunk, User
from app.services.business_access import allowed_client_ids, allowed_location_ids
from app.services.rbac import user_has_permissions


logger = logging.getLogger("edvatiq.ai.retrieval")


def document_access_conditions(db: Session, user: User):
    conditions = [Document.organization_id == user.organization_id]
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

    clients = allowed_client_ids(db, user)
    if clients is not None:
        client_docs = Document.entity_type.in_(["client", "patient"])
        conditions.append(or_(~client_docs, Document.entity_id.in_(clients) if clients else false()))
    return conditions


def retrieve(db: Session, user: User, query: str, limit: int = 8, document_id: str | None = None) -> dict:
    base = select(DocumentChunk, Document).join(Document, Document.id == DocumentChunk.document_id).where(
        Document.status == "ready", *document_access_conditions(db, user)
    )
    if document_id: base = base.where(Document.id == document_id)
    ranked: dict[str, float] = defaultdict(float)
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
    if client:
        try:
            embedding = client.embed([query])
            vector = embedding.vectors[0]
            provider_usage = {
                "embedding_tokens": embedding.input_tokens,
                "provider_requests": embedding.provider_requests,
            }
            distance = DocumentChunk.embedding_vector.cosine_distance(vector)
            with db.begin_nested():
                vector_rows = db.execute(
                    base.add_columns(distance.label("distance"))
                    .where(DocumentChunk.embedding_vector.is_not(None), distance <= 0.45)
                    .order_by(distance).limit(30)
                ).all()
            for rank, pair in enumerate(vector_rows, 1):
                ranked[pair[0].id] += 1 / (60 + rank)
                rows_by_id[pair[0].id] = pair[:2]
        except Exception as exc:
            logger.warning("embedding_search_unavailable error_type=%s", type(exc).__name__)

    if not ranked:
        fallback = db.execute(base.where(DocumentChunk.content.ilike(f"%{query}%")).limit(12)).all()
        for rank, pair in enumerate(fallback, 1):
            ranked[pair[0].id] = 1 / (60 + rank); rows_by_id[pair[0].id] = pair

    selected = []
    per_document = defaultdict(int)
    for chunk_id in sorted(ranked, key=ranked.get, reverse=True):
        document_key = rows_by_id[chunk_id][1].id
        if per_document[document_key] >= 2:
            continue
        selected.append(chunk_id)
        per_document[document_key] += 1
        if len(selected) >= max(1, min(limit, 12)):
            break
    citations = []
    for chunk_id in selected:
        chunk, document = rows_by_id[chunk_id]
        citations.append({
            "document_id": document.id, "document": document.name, "excerpt": chunk.content[:500],
            "page": chunk.page_number, "section": chunk.section,
            "href": f"/api/documents/{document.id}/download",
        })
    return {
        "query": query,
        "items": [{"content": item["excerpt"], **item} for item in citations],
        "citations": citations,
        "_provider_usage": provider_usage,
    }
