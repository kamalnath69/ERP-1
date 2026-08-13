"""Public website content, legal publication, and demo enquiry APIs."""
from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from pydantic import EmailStr, Field, field_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.models import DemoRequest, LegalDocument, PlatformSetting
from app.schemas.validation import RequestModel, valid_phone
from app.services.audit import log_action
from app.services.cursor_pagination import decode_cursor, encode_cursor, page_response, page_size
from app.services.email import send_email
from app.services.platform_security import require_platform_permission
from app.services.public_site import (
    LEGAL_PROFILE_KEY, VERSION_TWO_DOCUMENTS, content_hash,
    current_legal_documents, legal_document_payload, legal_profile,
    materialize_legal_content, missing_legal_profile_fields, public_legal_payload,
)


router = APIRouter(prefix="/public", tags=["public-site"])
super_router = APIRouter(prefix="/super-admin/legal", tags=["super-admin"])
now_utc = lambda: datetime.now(timezone.utc)


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    return (forwarded.split(",")[0].strip() if forwarded else request.client.host if request.client else None)


class LegalProfileBody(RequestModel):
    brand_name: str = Field(default="Edvatiq", min_length=2, max_length=120)
    legal_name: str = Field(min_length=2, max_length=220)
    registered_address: str = Field(min_length=8, max_length=1000)
    country: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    jurisdiction: str = Field(min_length=2, max_length=240)
    support_email: EmailStr
    privacy_email: EmailStr
    grievance_contact: str = Field(min_length=3, max_length=300)
    registration_identifiers: str | None = Field(default=None, max_length=500)
    version: int = Field(ge=1)


class LegalDraftBody(RequestModel):
    title: str = Field(min_length=3, max_length=180)
    content_markdown: str = Field(min_length=100, max_length=100_000)

    @field_validator("content_markdown")
    @classmethod
    def no_raw_html(cls, value: str) -> str:
        if re.search(r"<\s*/?\s*[a-z][^>]*>", value, re.IGNORECASE):
            raise ValueError("Raw HTML is not allowed in legal documents")
        return value


class LegalDraftUpdateBody(LegalDraftBody):
    version_lock: int = Field(ge=1)


class PublishBody(RequestModel):
    effective_at: datetime | None = None
    version_lock: int = Field(ge=1)


class DemoRequestBody(RequestModel):
    name: str = Field(min_length=2, max_length=160)
    work_email: EmailStr
    organization_name: str = Field(min_length=2, max_length=200)
    industry: Literal["gym", "salon", "clinic", "college", "other"]
    role: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    message: str | None = Field(default=None, max_length=3000)
    privacy_document_id: str = Field(min_length=1, max_length=100)
    privacy_acknowledged: Literal[True]
    website: str | None = Field(default=None, max_length=200)

    @field_validator("phone")
    @classmethod
    def phone_number(cls, value: str | None) -> str | None:
        return valid_phone(value)


class LeadStatusBody(RequestModel):
    status: Literal["new", "contacted", "qualified", "closed"]


def _notify_demo_request(request_id: str, recipient: str) -> None:
    with SessionLocal() as db:
        row = db.get(DemoRequest, request_id)
        if not row:
            return
        text = (
            f"New Edvatiq demo request\n\nName: {row.name}\nEmail: {row.work_email}\n"
            f"Organization: {row.organization_name}\nIndustry: {row.industry}\n"
            f"Role: {row.role or '-'}\nPhone: {row.phone or '-'}\n\n{row.message or ''}"
        )
        safe = {key: html.escape(str(value or "-")) for key, value in {
            "name": row.name, "email": row.work_email, "organization": row.organization_name,
            "industry": row.industry, "role": row.role, "phone": row.phone, "message": row.message,
        }.items()}
        body = (
            "<h2>New Edvatiq demo request</h2>"
            f"<p><strong>Name:</strong> {safe['name']}<br><strong>Email:</strong> {safe['email']}<br>"
            f"<strong>Organization:</strong> {safe['organization']}<br><strong>Industry:</strong> {safe['industry']}<br>"
            f"<strong>Role:</strong> {safe['role']}<br><strong>Phone:</strong> {safe['phone']}</p>"
            f"<p>{safe['message']}</p>"
        )
        subject_org = row.organization_name.replace("\r", " ").replace("\n", " ")
        if send_email(recipient, f"Demo request from {subject_org}", text, body, "demo_request"):
            row.notified_at = now_utc()
            db.commit()


@router.get("/site")
def public_site(response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    legal = public_legal_payload(db, include_content=False)
    return {
        "brand": legal["operator"].get("brand_name") or "Edvatiq",
        "support_email": legal["operator"].get("support_email") or "sales@edvatiq.com",
        "legal_ready": legal["ready"],
        "legal_documents": legal["documents"],
    }


@router.get("/legal/current")
def current_legal(response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    return public_legal_payload(db)


@router.get("/legal/{kind}/{version}")
def historical_legal(kind: Literal["terms", "privacy", "refund"], version: int, response: Response, db: Session = Depends(get_db)):
    row = db.execute(select(LegalDocument).where(
        LegalDocument.document_type == kind,
        LegalDocument.version == version,
        LegalDocument.status.in_(["published", "retired"]),
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Legal document not found")
    response.headers["Cache-Control"] = "public, max-age=3600"
    return legal_document_payload(row)


@router.post("/demo-requests", status_code=status.HTTP_201_CREATED)
def create_demo_request(body: DemoRequestBody, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    documents = current_legal_documents(db)
    privacy = documents.get("privacy")
    if not privacy or privacy.id != body.privacy_document_id:
        raise HTTPException(409, "Privacy Policy changed. Review the current version and try again")
    # Honeypot submissions get the same response without creating a lead.
    if body.website:
        return {"received": True}
    ip = client_ip(request) or ""
    ip_hash = hashlib.sha256(f"{settings.JWT_SECRET_KEY}:{ip}".encode()).hexdigest() if ip else None
    cutoff = now_utc() - timedelta(minutes=15)
    recent = db.scalar(select(func.count(DemoRequest.id)).where(
        DemoRequest.ip_hash == ip_hash,
        DemoRequest.created_at >= cutoff,
    )) if ip_hash else 0
    if recent and recent >= 5:
        raise HTTPException(429, "Too many demo requests. Please wait before trying again")
    row = DemoRequest(
        name=body.name,
        work_email=str(body.work_email).lower(),
        organization_name=body.organization_name,
        industry=body.industry,
        role=body.role,
        phone=body.phone,
        message=body.message,
        privacy_document_id=privacy.id,
        ip_hash=ip_hash,
        user_agent=(request.headers.get("user-agent") or "")[:300] or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    profile, _ = legal_profile(db)
    background.add_task(_notify_demo_request, row.id, profile.get("support_email") or "sales@edvatiq.com")
    return {"id": row.id, "received": True}


@super_router.get("")
def legal_admin(actor=Depends(require_platform_permission("settings.manage")), db: Session = Depends(get_db)):
    profile, setting = legal_profile(db)
    rows = db.execute(select(LegalDocument).order_by(
        LegalDocument.document_type, LegalDocument.version.desc(),
    )).scalars()
    return {
        "profile": profile,
        "profile_version": setting.version if setting else 1,
        "missing_profile_fields": missing_legal_profile_fields(profile),
        "ready": public_legal_payload(db, include_content=False)["ready"],
        "documents": [legal_document_payload(row) for row in rows],
    }


@super_router.put("/profile")
def update_legal_profile(body: LegalProfileBody, actor=Depends(require_platform_permission("settings.manage")), db: Session = Depends(get_db)):
    row = db.execute(select(PlatformSetting).where(PlatformSetting.key == LEGAL_PROFILE_KEY).with_for_update()).scalar_one_or_none()
    if row and row.version != body.version:
        raise HTTPException(409, "Legal profile changed. Refresh and try again")
    values = body.model_dump(exclude={"version"}, mode="json")
    if row:
        row.value = values
        row.version += 1
    else:
        row = PlatformSetting(key=LEGAL_PROFILE_KEY, value=values, version=1)
        db.add(row)
    log_action(db, organization_id=None, user_id=actor.id, action="platform.legal_profile_updated", resource_type="platform_setting", resource_id=LEGAL_PROFILE_KEY)
    db.commit()
    return {"profile": values, "version": row.version}


@super_router.post("/documents/version-two-drafts", status_code=status.HTTP_201_CREATED)
def create_version_two_legal_drafts(actor=Depends(require_platform_permission("settings.manage")), db: Session = Depends(get_db)):
    created = []
    existing = []
    blocked = []

    for kind, spec in VERSION_TWO_DOCUMENTS.items():
        version_two = db.execute(select(LegalDocument).where(
            LegalDocument.document_type == kind,
            LegalDocument.version == 2,
        )).scalar_one_or_none()
        if version_two:
            existing.append(legal_document_payload(version_two))
            continue

        open_draft = db.execute(select(LegalDocument).where(
            LegalDocument.document_type == kind,
            LegalDocument.status == "draft",
        )).scalar_one_or_none()
        latest_version = db.scalar(select(func.max(LegalDocument.version)).where(
            LegalDocument.document_type == kind,
        ))
        if open_draft or latest_version != 1:
            blocked.append({
                "type": kind,
                "reason": "Finish the existing draft first" if open_draft else "Version 1 must exist before Version 2",
            })
            continue

        body = spec["content"].strip()
        row = LegalDocument(
            document_type=kind,
            version=2,
            title=spec["title"],
            content_markdown=body,
            content_hash=content_hash(body),
            status="draft",
        )
        db.add(row)
        db.flush()
        log_action(
            db,
            organization_id=None,
            user_id=actor.id,
            action="platform.legal_v2_draft_created",
            resource_type="legal_document",
            resource_id=row.id,
            meta={"type": kind, "version": 2},
        )
        created.append(legal_document_payload(row))

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Legal drafts changed. Refresh and try again")
    return {"created": created, "existing": existing, "blocked": blocked}


@super_router.post("/documents/{kind}/drafts", status_code=status.HTTP_201_CREATED)
def create_legal_draft(kind: Literal["terms", "privacy", "refund"], body: LegalDraftBody, actor=Depends(require_platform_permission("settings.manage")), db: Session = Depends(get_db)):
    if db.execute(select(LegalDocument.id).where(
        LegalDocument.document_type == kind, LegalDocument.status == "draft",
    )).first():
        raise HTTPException(409, "Finish or publish the existing draft first")
    next_version = (db.scalar(select(func.max(LegalDocument.version)).where(LegalDocument.document_type == kind)) or 0) + 1
    row = LegalDocument(
        document_type=kind,
        version=next_version,
        title=body.title,
        content_markdown=body.content_markdown,
        content_hash=content_hash(body.content_markdown),
        status="draft",
    )
    db.add(row)
    db.flush()
    log_action(db, organization_id=None, user_id=actor.id, action="platform.legal_draft_created", resource_type="legal_document", resource_id=row.id, meta={"type": kind, "version": next_version})
    db.commit()
    db.refresh(row)
    return legal_document_payload(row)


@super_router.put("/documents/{document_id}")
def update_legal_draft(document_id: str, body: LegalDraftUpdateBody, actor=Depends(require_platform_permission("settings.manage")), db: Session = Depends(get_db)):
    row = db.get(LegalDocument, document_id)
    if not row:
        raise HTTPException(404, "Legal document not found")
    if row.status != "draft":
        raise HTTPException(409, "Published legal documents are immutable. Create a new draft")
    if row.version_lock != body.version_lock:
        raise HTTPException(409, "This legal draft changed. Refresh before saving your edits")
    row.title = body.title
    row.content_markdown = body.content_markdown
    row.content_hash = content_hash(body.content_markdown)
    row.version_lock += 1
    log_action(db, organization_id=None, user_id=actor.id, action="platform.legal_draft_updated", resource_type="legal_document", resource_id=row.id, meta={"type": row.document_type, "version": row.version})
    db.commit()
    db.refresh(row)
    return legal_document_payload(row)


@super_router.post("/documents/{document_id}/publish")
def publish_legal_document(document_id: str, body: PublishBody, actor=Depends(require_platform_permission("settings.manage")), db: Session = Depends(get_db)):
    row = db.get(LegalDocument, document_id)
    if not row:
        raise HTTPException(404, "Legal document not found")
    if row.status != "draft":
        raise HTTPException(409, "Only a draft can be published")
    if row.version_lock != body.version_lock:
        raise HTTPException(409, "This legal draft changed. Refresh before publishing")
    profile, _ = legal_profile(db)
    missing = missing_legal_profile_fields(profile)
    if missing:
        raise HTTPException(409, f"Complete the legal profile before publishing: {', '.join(missing)}")
    rendered = materialize_legal_content(row.content_markdown, profile)
    if re.search(r"{{[a-z_]+}}", rendered):
        raise HTTPException(409, "The document contains unresolved legal profile placeholders")
    current = db.execute(select(LegalDocument).where(
        LegalDocument.document_type == row.document_type,
        LegalDocument.status == "published",
    ).with_for_update()).scalar_one_or_none()
    if current:
        current.status = "retired"
        db.flush()
    published_at = now_utc()
    row.content_markdown = rendered
    row.content_hash = content_hash(rendered)
    row.status = "published"
    row.effective_at = body.effective_at or published_at
    row.published_at = published_at
    row.published_by_user_id = actor.id
    log_action(db, organization_id=None, user_id=actor.id, action="platform.legal_document_published", resource_type="legal_document", resource_id=row.id, meta={"type": row.document_type, "version": row.version, "hash": row.content_hash})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Another legal version was published. Refresh and try again")
    db.refresh(row)
    return legal_document_payload(row)


def _lead_payload(row: DemoRequest) -> dict:
    return {
        "id": row.id, "name": row.name, "work_email": row.work_email,
        "organization_name": row.organization_name, "industry": row.industry,
        "role": row.role, "phone": row.phone, "message": row.message,
        "status": row.status, "created_at": row.created_at, "notified_at": row.notified_at,
    }


@super_router.get("/demo-requests")
def list_demo_requests(
    status_filter: Literal["all", "new", "contacted", "qualified", "closed"] = Query("all", alias="status"),
    q: str | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    actor=Depends(require_platform_permission("overview.view")),
    db: Session = Depends(get_db),
):
    filters = {"status": status_filter, "q": q}
    values = decode_cursor(cursor, scope="super-admin.demo-requests", organization_id=None, filters=filters)
    query = select(DemoRequest)
    if status_filter != "all":
        query = query.where(DemoRequest.status == status_filter)
    if q:
        term = f"%{q.strip()}%"
        query = query.where(or_(DemoRequest.name.ilike(term), DemoRequest.work_email.ilike(term), DemoRequest.organization_name.ilike(term)))
    if values:
        at = datetime.fromisoformat(str(values["at"]))
        row_id = str(values["id"])
        query = query.where(or_(DemoRequest.created_at < at, and_(DemoRequest.created_at == at, DemoRequest.id < row_id)))
    size = page_size(limit)
    rows = list(db.execute(query.order_by(DemoRequest.created_at.desc(), DemoRequest.id.desc()).limit(size + 1)).scalars())
    has_more = len(rows) > size
    rows = rows[:size]
    next_cursor = encode_cursor(scope="super-admin.demo-requests", organization_id=None, filters=filters, values={"at": rows[-1].created_at.isoformat(), "id": rows[-1].id}) if has_more and rows else None
    return page_response([_lead_payload(row) for row in rows], next_cursor)


@super_router.patch("/demo-requests/{request_id}")
def update_demo_request(request_id: str, body: LeadStatusBody, actor=Depends(require_platform_permission("settings.manage")), db: Session = Depends(get_db)):
    row = db.get(DemoRequest, request_id)
    if not row:
        raise HTTPException(404, "Demo request not found")
    row.status = body.status
    log_action(db, organization_id=None, user_id=actor.id, action="platform.demo_request_updated", resource_type="demo_request", resource_id=row.id, meta={"status": body.status})
    db.commit()
    return _lead_payload(row)
