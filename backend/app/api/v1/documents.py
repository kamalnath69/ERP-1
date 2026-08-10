"""Tenant-safe document uploads, retrieval, and client communications."""
import hashlib
import math
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.business import serialize
from app.core.config import ROOT_DIR, settings
from app.core.database import get_db
from app.core.deps import require_entitlements, require_permissions
from app.models import Client, Document, DocumentChunk, Job, Organization, OutboundMessage
from app.services.business_access import ensure_client_access, ensure_location, tenant_get
from app.services.cursor_pagination import decode_cursor, encode_cursor, page_size
from app.services.entitlements import entitlement_value
from app.services.rbac import user_has_permissions

router = APIRouter(tags=["documents-and-communications"])
STORAGE_DIR = ROOT_DIR / "storage"
ALLOWED_TYPES = {
    "application/pdf": ".pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt", "image/jpeg": ".jpg", "image/png": ".png",
}
MAX_BYTES = 20 * 1024 * 1024


class MessageBody(BaseModel):
    client_id: str
    channel: str = "whatsapp"
    body: str = Field(min_length=1, max_length=800)
    subject: str | None = None
    template: str | None = None
    template_language: str | None = None
    template_variables: list[str] = Field(default_factory=list)
    location_id: str | None = None
    idempotency_key: str = Field(min_length=8, max_length=120)
    confirmed: bool = False


@router.get("/documents")
def list_documents(entity_type: str | None = None, entity_id: str | None = None, user=Depends(require_permissions("documents.view")), db: Session = Depends(get_db)):
    from app.ai.retrieval import document_access_conditions
    stmt = select(Document).where(*document_access_conditions(db, user))
    if entity_type: stmt = stmt.where(Document.entity_type == entity_type)
    if entity_id: stmt = stmt.where(Document.entity_id == entity_id)
    return [serialize(row, {"object_key": None}) for row in db.execute(stmt.order_by(Document.created_at.desc()).limit(300)).scalars()]


@router.get("/documents/page")
def document_page(
    entity_type: str | None = None,
    entity_id: str | None = None,
    status: str | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user=Depends(require_permissions("documents.view")),
    db: Session = Depends(get_db),
):
    from app.ai.retrieval import document_access_conditions
    access_conditions = document_access_conditions(db, user)
    filters = {"entity_type": entity_type, "entity_id": entity_id, "status": status, "q": q}
    values = decode_cursor(cursor, scope="documents.page", organization_id=user.organization_id, filters=filters)
    statement = select(Document).where(*access_conditions)
    if entity_type:
        statement = statement.where(Document.entity_type == entity_type)
    if entity_id:
        statement = statement.where(Document.entity_id == entity_id)
    if status and status != "all":
        statement = statement.where(Document.status == status)
    if q:
        statement = statement.where(func.lower(Document.name).like(f"%{' '.join(q.casefold().split())}%"))
    if values:
        pivot_at = datetime.fromisoformat(str(values["at"]))
        statement = statement.where(or_(
            Document.created_at < pivot_at,
            and_(Document.created_at == pivot_at, Document.id < values["id"]),
        ))
    size = page_size(limit)
    rows = list(db.execute(statement.order_by(Document.created_at.desc(), Document.id.desc()).limit(size + 1)).scalars())
    has_more = len(rows) > size
    rows = rows[:size]
    next_cursor = encode_cursor(
        scope="documents.page",
        organization_id=user.organization_id,
        filters=filters,
        values={"at": rows[-1].created_at.isoformat(), "id": rows[-1].id},
    ) if has_more and rows else None
    summary = db.execute(select(
        func.count(Document.id),
        func.coalesce(func.sum(case((Document.status == "ready", 1), else_=0)), 0),
        func.coalesce(func.sum(case((Document.status.in_(("pending", "processing")), 1), else_=0)), 0),
        func.coalesce(func.sum(Document.size_bytes), 0),
    ).where(*access_conditions)).one()
    return {
        "items": [serialize(row, {"object_key": None}) for row in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "summary": {
            "files": int(summary[0] or 0),
            "ready": int(summary[1] or 0),
            "processing": int(summary[2] or 0),
            "storage_bytes": int(summary[3] or 0),
        },
    }


@router.post("/documents/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...), location_id: str | None = Form(None), entity_type: str | None = Form(None),
    entity_id: str | None = Form(None), visibility: str = Form("team"),
    user=Depends(require_permissions("documents.manage")), db: Session = Depends(get_db),
):
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_TYPES: raise HTTPException(415, "Only PDF, DOCX, TXT, JPG, and PNG files are accepted")
    if location_id: ensure_location(db, user, location_id)
    if visibility not in {"team", "managers", "author_only", "clinical"}: raise HTTPException(422, "Invalid document visibility")
    if visibility == "clinical" and not user_has_permissions(db, user, ["clinical.write"]): raise HTTPException(403, "Clinical document access is required")
    if entity_type in {"client", "patient"} and entity_id:
        ensure_client_access(db, user, tenant_get(db, Client, entity_id, user))
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES: raise HTTPException(413, "Document exceeds the 20 MB limit")
    if not content: raise HTTPException(400, "Document is empty")
    used = db.scalar(select(func.coalesce(func.sum(Document.size_bytes), 0)).where(Document.organization_id == user.organization_id)) or 0
    organization = db.get(Organization, user.organization_id)
    storage_limit_mb = entitlement_value(db, organization, "limits.storage_mb")
    if storage_limit_mb is not None and used + len(content) > int(storage_limit_mb) * 1024 * 1024:
        raise HTTPException(402, "Document storage allowance reached for the current plan")
    if content.startswith((b"MZ", b"\x7fELF")): raise HTTPException(400, "Executable content is not allowed")
    checksum = hashlib.sha256(content).hexdigest(); safe_name = Path(file.filename or "document").name
    object_key = f"{user.organization_id}/{secrets.token_hex(12)}{ALLOWED_TYPES[content_type]}"
    if settings.S3_ENDPOINT_URL and not settings.PROVIDER_MOCK_MODE:
        import boto3
        client = boto3.client("s3", endpoint_url=settings.S3_ENDPOINT_URL, aws_access_key_id=settings.S3_ACCESS_KEY_ID, aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY)
        client.put_object(Bucket=settings.S3_BUCKET, Key=object_key, Body=content, ContentType=content_type)
    else:
        target = STORAGE_DIR / object_key; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
    row = Document(
        organization_id=user.organization_id, location_id=location_id, uploaded_by_user_id=user.id,
        entity_type=entity_type, entity_id=entity_id, name=safe_name, object_key=object_key,
        content_type=content_type, size_bytes=len(content), checksum=checksum, visibility=visibility,
    )
    db.add(row); db.flush()
    db.add(Job(organization_id=user.organization_id, kind="process_document", payload={"document_id": row.id}, run_at=datetime.now(timezone.utc), idempotency_key=f"document-{row.id}"))
    db.commit(); db.refresh(row); return serialize(row, {"object_key": None})


@router.get("/documents/{document_id}/download")
def download_document(document_id: str, user=Depends(require_permissions("documents.view")), db: Session = Depends(get_db)):
    from app.ai.retrieval import document_access_conditions
    row = db.execute(select(Document).where(Document.id == document_id, *document_access_conditions(db, user))).scalar_one_or_none()
    if not row: raise HTTPException(404, "Document not found")
    if settings.S3_ENDPOINT_URL and not settings.PROVIDER_MOCK_MODE:
        import boto3
        client = boto3.client("s3", endpoint_url=settings.S3_ENDPOINT_URL, aws_access_key_id=settings.S3_ACCESS_KEY_ID, aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY)
        url = client.generate_presigned_url("get_object", Params={"Bucket": settings.S3_BUCKET, "Key": row.object_key}, ExpiresIn=300)
        return RedirectResponse(url)
    path = (STORAGE_DIR / row.object_key).resolve()
    if STORAGE_DIR.resolve() not in path.parents or not path.exists(): raise HTTPException(404, "Stored document is unavailable")
    return FileResponse(path, media_type=row.content_type, filename=row.name)


@router.post("/documents/{document_id}/reindex", status_code=202)
def reindex_document(document_id: str, user=Depends(require_permissions("documents.manage")), _plan=Depends(require_entitlements("documents.knowledge")), db: Session = Depends(get_db)):
    from app.ai.retrieval import document_access_conditions
    row = db.execute(select(Document).where(Document.id == document_id, *document_access_conditions(db, user))).scalar_one_or_none()
    if not row: raise HTTPException(404, "Document not found")
    row.status = "pending"; row.error = None; row.embedding_version += 1
    now = datetime.now(timezone.utc)
    db.add(Job(organization_id=user.organization_id, kind="process_document", payload={"document_id": row.id},
               run_at=now, idempotency_key=f"document-reindex-{row.id}-{row.embedding_version}"))
    db.commit(); return {"status": "pending"}


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, user=Depends(require_permissions("documents.manage")), db: Session = Depends(get_db)):
    from app.ai.retrieval import document_access_conditions
    row = db.execute(select(Document).where(Document.id == document_id, *document_access_conditions(db, user))).scalar_one_or_none()
    if not row: raise HTTPException(404, "Document not found")
    if settings.S3_ENDPOINT_URL and not settings.PROVIDER_MOCK_MODE:
        import boto3
        boto3.client("s3", endpoint_url=settings.S3_ENDPOINT_URL, aws_access_key_id=settings.S3_ACCESS_KEY_ID,
                     aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY).delete_object(Bucket=settings.S3_BUCKET, Key=row.object_key)
    else:
        path = (STORAGE_DIR / row.object_key).resolve()
        if STORAGE_DIR.resolve() in path.parents and path.exists(): path.unlink()
    db.delete(row); db.commit(); return {"ok": True}


@router.get("/documents/search")
def search_documents(q: str, user=Depends(require_permissions("documents.view")), _plan=Depends(require_entitlements("documents.knowledge")), db: Session = Depends(get_db)):
    if not q.strip(): return []
    from app.ai.retrieval import retrieve
    return retrieve(db, user, q)["items"]


@router.get("/messages")
def list_messages(user=Depends(require_permissions("notifications.send")), db: Session = Depends(get_db)):
    return [serialize(row) for row in db.execute(select(OutboundMessage).where(OutboundMessage.organization_id == user.organization_id).order_by(OutboundMessage.created_at.desc()).limit(200)).scalars()]


@router.get("/communication/status")
def communication_status(user=Depends(require_permissions("settings.manage"))):
    whatsapp_ready = bool(settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID)
    email_ready = bool(settings.RESEND_API_KEY and settings.RESEND_FROM_EMAIL)
    return {
        "security_email": {"ready": email_ready},
        "whatsapp": {
            "ready": whatsapp_ready,
            "reminders_enabled": settings.WHATSAPP_REMINDERS_ENABLED,
            "automations": [
                "Appointment booking confirmations",
                "Appointment reminders within 24 hours",
                "Important appointment status changes",
                "Gym membership lifecycle updates",
                "Gym membership reminders 7 days and 1 day before expiry",
            ],
        },
    }


@router.post("/messages", status_code=202)
def send_message(body: MessageBody, user=Depends(require_permissions("notifications.send")), db: Session = Depends(get_db)):
    if not body.confirmed: raise HTTPException(409, "Message preview must be confirmed before sending")
    existing = db.execute(select(OutboundMessage).where(OutboundMessage.organization_id == user.organization_id, OutboundMessage.idempotency_key == body.idempotency_key)).scalar_one_or_none()
    if existing: return serialize(existing)
    client = tenant_get(db, Client, body.client_id, user)
    if body.location_id: ensure_location(db, user, body.location_id)
    if body.channel != "whatsapp": raise HTTPException(400, "Client updates are sent through WhatsApp")
    if not client.whatsapp_consent or not client.phone: raise HTTPException(409, "WhatsApp consent and phone are required")
    organization = db.get(Organization, user.organization_id)
    template = body.template or settings.WHATSAPP_TEMPLATE_CLIENT_UPDATE
    variables = body.template_variables or [client.first_name, body.body, organization.name]
    row = OutboundMessage(
        organization_id=user.organization_id, location_id=body.location_id, client_id=client.id,
        channel="whatsapp", recipient=client.phone, template=template,
        template_language=body.template_language or settings.WHATSAPP_TEMPLATE_LANGUAGE,
        template_variables=variables, subject=body.subject, body=body.body,
        scheduled_for=datetime.now(timezone.utc), idempotency_key=body.idempotency_key,
    )
    db.add(row); db.flush(); db.add(Job(organization_id=user.organization_id, kind="send_message", payload={"message_id": row.id}, run_at=datetime.now(timezone.utc), idempotency_key=f"send-{row.id}"))
    db.commit(); db.refresh(row); return serialize(row)


def _embedding(text: str):
    if not settings.AI_API_KEY: return None
    from openai import OpenAI
    client = OpenAI(api_key=settings.AI_API_KEY, base_url=settings.OPENAI_BASE_URL or None)
    return client.embeddings.create(model=settings.AI_EMBEDDING_MODEL, input=text).data[0].embedding


def _cosine_distance(left, right):
    dot = sum(a * b for a, b in zip(left, right)); norm_left = math.sqrt(sum(a * a for a in left)); norm_right = math.sqrt(sum(b * b for b in right))
    return 1 - dot / (norm_left * norm_right) if norm_left and norm_right else 1
