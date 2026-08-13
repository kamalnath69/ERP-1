"""College ERP push credentials and the public integration contract."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_entitlements, require_permissions
from app.models import (
    CollegeDataConnector, CollegeExamCycle, CollegeImportRun,
    CollegeIntegrationCredential, CollegeIntegrationRateBucket,
    DataExchangeRow, DataExchangeRun, Organization, User,
)
from app.schemas.validation import RequestModel
from app.services.audit import log_action
from app.services.access_policy import policy_v2_enabled, resolve_policy_context
from app.services.college import require_college, tenant_row
from app.services.college_access import resolve_college_access
from app.services.college_imports import RESOURCE_FIELDS, commit_run, stage_rows
from app.services.data_exchange import (
    ingest_assessment_metric_records, ingest_exchange_records, resource_schema,
)


RESOURCE_TYPES = (
    "departments", "programs", "terms", "cohorts", "courses", "students",
    "term_results", "attendance", "skills", "assessments", "internship_clearance",
    "assessment_marks", "exam_cycles",
)
ResourceType = Literal[
    "departments", "programs", "terms", "cohorts", "courses", "students",
    "term_results", "attendance", "skills", "assessments", "internship_clearance",
    "assessment_marks", "exam_cycles",
]
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 500
REQUESTS_PER_MINUTE = 60
now_utc = lambda: datetime.now(timezone.utc)
bearer = HTTPBearer(auto_error=False)


credential_router = APIRouter(
    prefix="/college/integrations/credentials",
    tags=["college-integrations"],
    dependencies=[Depends(require_entitlements("module.college"))],
)
integration_router = APIRouter(prefix="/integrations/v1", tags=["college-erp-api"])


def _require_credential_administration(db: Session, user: User) -> None:
    """Require both the Data domain and the explicit credential safeguard."""
    require_college(db, user)
    resolve_college_access(db, user, "data")
    if policy_v2_enabled(db, user.organization_id):
        context = resolve_policy_context(db, user)
        if not context.has_sensitive("college.integrations.manage"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Integration credential access is required")


class CredentialBody(RequestModel):
    name: str = Field(min_length=2, max_length=120)
    scopes: list[ResourceType] = Field(min_length=1, max_length=len(RESOURCE_TYPES))
    expires_at: datetime

    @model_validator(mode="after")
    def validate_credential(self):
        current = now_utc()
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
            self.expires_at = expires_at
        if expires_at <= current + timedelta(minutes=5):
            raise ValueError("Expiry must be at least five minutes in the future")
        if expires_at > current + timedelta(days=730):
            raise ValueError("Expiry cannot be more than two years in the future")
        self.scopes = list(dict.fromkeys(self.scopes))
        return self


class RotateCredentialBody(RequestModel):
    expires_at: datetime | None = None
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_expiry(self):
        if self.expires_at:
            if self.expires_at.tzinfo is None:
                self.expires_at = self.expires_at.replace(tzinfo=timezone.utc)
            if self.expires_at <= now_utc() + timedelta(minutes=5):
                raise ValueError("Expiry must be at least five minutes in the future")
        return self


class RevokeCredentialBody(RequestModel):
    version: int = Field(ge=1)


class PushBatchBody(RequestModel):
    records: list[dict] = Field(min_length=1, max_length=MAX_RECORDS)
    source_cursor: str | None = Field(default=None, max_length=500)
    sent_at: datetime | None = None


def _credential_payload(row: CollegeIntegrationCredential) -> dict:
    active = row.revoked_at is None and row.expires_at > now_utc()
    return {
        "id": row.id,
        "name": row.name,
        "key_prefix": row.key_prefix,
        "scopes": row.scopes,
        "expires_at": row.expires_at,
        "revoked_at": row.revoked_at,
        "last_used_at": row.last_used_at,
        "created_at": row.created_at,
        "version": row.version,
        "status": "active" if active else "revoked" if row.revoked_at else "expired",
    }


def _run_payload(run: CollegeImportRun, *, replayed: bool = False) -> dict:
    return {
        "run_id": run.id,
        "resource": run.resource_type,
        "status": run.status,
        "received_count": run.row_count,
        "committed_count": run.committed_count,
        "failed_count": run.failed_count,
        "errors": [
            {"row": item.get("row"), "errors": list(item.get("errors") or [])[:10]}
            for item in (run.validation_errors or [])[:500]
        ],
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        "replayed": replayed,
    }


def _exchange_result_payload(db: Session, run: DataExchangeRun, *, replayed: bool = False) -> dict:
    failed = int(run.invalid_count or 0) + int(run.conflict_count or 0)
    if run.committed_count and failed:
        public_status = "partial"
    elif run.committed_count:
        public_status = "committed"
    else:
        public_status = "invalid"
    rows = list(db.scalars(select(DataExchangeRow).where(
        DataExchangeRow.organization_id == run.organization_id,
        DataExchangeRow.run_id == run.id,
        DataExchangeRow.status.in_(("invalid", "conflict")),
    ).order_by(DataExchangeRow.row_number).limit(500)))
    return {
        "run_id": run.id,
        "resource": run.resource_key,
        "status": public_status,
        "received_count": int(run.row_count or 0),
        "committed_count": int(run.committed_count or 0),
        "failed_count": failed,
        "errors": [{"row": row.row_number, "errors": list(row.errors or [])[:10]} for row in rows],
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        "replayed": replayed,
    }


def _issue_token() -> tuple[str, str, str]:
    prefix = secrets.token_hex(6)
    token = f"edv_college_{prefix}_{secrets.token_urlsafe(32)}"
    return token, prefix, hashlib.sha256(token.encode("utf-8")).hexdigest()


def _extract_prefix(token: str) -> str | None:
    parts = token.split("_", 3)
    if len(parts) != 4 or parts[0] != "edv" or parts[1] != "college":
        return None
    return parts[2]


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:80]
    return request.client.host[:80] if request.client else None


def _require_integration_credential(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Session = Depends(get_db),
) -> CollegeIntegrationCredential:
    token = credentials.credentials if credentials else ""
    prefix = _extract_prefix(token)
    if not prefix:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "A valid ERP integration credential is required")
    row = db.execute(select(CollegeIntegrationCredential).where(
        CollegeIntegrationCredential.key_prefix == prefix,
    )).scalar_one_or_none()
    supplied_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if not row or not hmac.compare_digest(row.token_hash if row else "", supplied_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "A valid ERP integration credential is required")
    organization = db.get(Organization, row.organization_id)
    if not organization or organization.status.value in {"suspended", "cancelled"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This organization cannot receive integration data")
    current = now_utc()
    if row.revoked_at:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This ERP integration credential was revoked")
    if row.expires_at <= current:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This ERP integration credential expired")
    row.last_used_at = current
    row.last_ip = _client_ip(request)
    request.state.tenant_id = row.organization_id
    request.state.integration_credential = row
    return row


def _consume_rate_limit(db: Session, credential: CollegeIntegrationCredential, records: int) -> None:
    current = now_utc()
    window_start = current.replace(second=0, microsecond=0)
    statement = insert(CollegeIntegrationRateBucket).values(
        id=str(uuid.uuid4()),
        credential_id=credential.id,
        window_start=window_start,
        request_count=1,
        record_count=records,
    ).on_conflict_do_update(
        constraint="uq_college_integration_rate_window",
        set_={
            "request_count": CollegeIntegrationRateBucket.request_count + 1,
            "record_count": CollegeIntegrationRateBucket.record_count + records,
        },
        where=CollegeIntegrationRateBucket.request_count < REQUESTS_PER_MINUTE,
    ).returning(CollegeIntegrationRateBucket.request_count)
    count = db.execute(statement).scalar_one_or_none()
    if count is None:
        db.rollback()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "This credential has reached its 60 requests per minute limit",
            headers={"Retry-After": "60"},
        )
    db.commit()


def _stage_dynamic_assessment_push(
    db: Session,
    credential: CollegeIntegrationCredential,
    records: list[dict],
    *,
    scoped_key: str,
    request_hash: str,
) -> DataExchangeRun:
    return ingest_assessment_metric_records(
        db,
        organization_id=credential.organization_id,
        records=records,
        source_type="erp_push",
        idempotency_key=scoped_key,
        request_hash=request_hash,
        access_mapping={},
        auto_commit=True,
    )


@credential_router.get("")
def list_credentials(
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.integrations.manage")),
):
    _require_credential_administration(db, user)
    rows = db.execute(select(CollegeIntegrationCredential).where(
        CollegeIntegrationCredential.organization_id == user.organization_id,
    ).order_by(CollegeIntegrationCredential.created_at.desc())).scalars()
    return {"items": [_credential_payload(row) for row in rows]}


@credential_router.post("", status_code=status.HTTP_201_CREATED)
def create_credential(
    body: CredentialBody,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.integrations.manage")),
):
    _require_credential_administration(db, user)
    token, prefix, token_hash = _issue_token()
    connector = CollegeDataConnector(
        organization_id=user.organization_id,
        name=body.name,
        connector_type="erp_push",
        auth_mode="bearer",
        mapping={"resources": body.scopes},
        pagination={},
        sync_interval_hours=6,
        status="ready",
        is_active=True,
    )
    db.add(connector)
    db.flush()
    row = CollegeIntegrationCredential(
        organization_id=user.organization_id,
        connector_id=connector.id,
        name=body.name,
        key_prefix=prefix,
        token_hash=token_hash,
        scopes=body.scopes,
        expires_at=body.expires_at,
        created_by_user_id=user.id,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A push credential with this name already exists")
    log_action(
        db, organization_id=user.organization_id, user_id=user.id,
        action="college.integration_credential.created",
        resource_type="college_integration_credential", resource_id=row.id,
        permission="college.integrations.manage", meta={"scopes": body.scopes, "expires_at": body.expires_at.isoformat()},
    )
    db.commit()
    db.refresh(row)
    response.headers["Cache-Control"] = "no-store"
    return {**_credential_payload(row), "secret": token}


@credential_router.post("/{credential_id}/rotate")
def rotate_credential(
    credential_id: str,
    body: RotateCredentialBody,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.integrations.manage")),
):
    _require_credential_administration(db, user)
    row = tenant_row(db, CollegeIntegrationCredential, credential_id, user, "Integration credential")
    if row.version != body.version:
        raise HTTPException(status.HTTP_409_CONFLICT, "The credential changed. Refresh and try again")
    if row.revoked_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "A revoked credential cannot be rotated")
    token, prefix, token_hash = _issue_token()
    row.key_prefix = prefix
    row.token_hash = token_hash
    if body.expires_at:
        row.expires_at = body.expires_at
    row.version += 1
    log_action(
        db, organization_id=user.organization_id, user_id=user.id,
        action="college.integration_credential.rotated",
        resource_type="college_integration_credential", resource_id=row.id,
        permission="college.integrations.manage", meta={"expires_at": row.expires_at.isoformat()},
    )
    db.commit()
    db.refresh(row)
    response.headers["Cache-Control"] = "no-store"
    return {**_credential_payload(row), "secret": token}


@credential_router.delete("/{credential_id}")
def revoke_credential(
    credential_id: str,
    body: RevokeCredentialBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permissions("college.integrations.manage")),
):
    _require_credential_administration(db, user)
    row = tenant_row(db, CollegeIntegrationCredential, credential_id, user, "Integration credential")
    if row.version != body.version:
        raise HTTPException(status.HTTP_409_CONFLICT, "The credential changed. Refresh and try again")
    if not row.revoked_at:
        row.revoked_at = now_utc()
        row.version += 1
        connector = db.get(CollegeDataConnector, row.connector_id)
        if connector:
            connector.is_active = False
            connector.status = "revoked"
        log_action(
            db, organization_id=user.organization_id, user_id=user.id,
            action="college.integration_credential.revoked",
            resource_type="college_integration_credential", resource_id=row.id,
            permission="college.integrations.manage",
        )
        db.commit()
    return _credential_payload(row)


@integration_router.get("/college/schemas/{resource}")
def integration_resource_schema(
    resource: ResourceType,
    cycle_id: str | None = None,
    cycle_code: str | None = None,
    credential: CollegeIntegrationCredential = Depends(_require_integration_credential),
    db: Session = Depends(get_db),
):
    if resource not in credential.scopes:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"This credential cannot access {resource}")
    _consume_rate_limit(db, credential, 0)
    if resource == "assessment_marks" and not cycle_id and cycle_code:
        cycle_id = db.scalar(select(CollegeExamCycle.id).where(
            CollegeExamCycle.organization_id == credential.organization_id,
            CollegeExamCycle.code == str(cycle_code).strip().upper().replace("-", "_"),
        ))
        if not cycle_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Exam cycle not found")
    if resource == "assessments":
        fields = RESOURCE_FIELDS["assessments"]
        return {
            "resource": {"key": resource, "label": "Placement assessments", "methods": ["api_push"]},
            "schema_version": "legacy-placement-1",
            "fields": [{"key": key, "label": key.replace("_", " ").title(), "type": "text"} for key in fields],
            "deprecation": "Use assessment_marks for institution-configured academic, coding, and placement metrics.",
        }
    return resource_schema(
        db,
        credential.organization_id,
        resource,
        {"cycle_id": cycle_id} if cycle_id else {},
    )


@integration_router.post("/college/{resource}")
async def push_college_records(
    request: Request,
    body: PushBatchBody,
    resource: ResourceType = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=120),
    credential: CollegeIntegrationCredential = Depends(_require_integration_credential),
    db: Session = Depends(get_db),
):
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_REQUEST_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Request body cannot exceed 2 MB")
    canonical = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    if len(canonical) > MAX_REQUEST_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Request body cannot exceed 2 MB")
    if resource not in credential.scopes:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"This credential cannot write {resource}")
    _consume_rate_limit(db, credential, len(body.records))

    missing_external_ids = [
        index + 1 for index, row in enumerate(body.records)
        if resource not in {"assessment_marks", "exam_cycles"} and not str(row.get("external_id") or "").strip()
    ]
    if missing_external_ids:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"message": "Every pushed record requires external_id", "rows": missing_external_ids[:100]},
        )
    request_hash = hashlib.sha256(canonical).hexdigest()
    scoped_key = f"push:{credential.id}:{resource}:{idempotency_key}"
    if resource in {"assessment_marks", "exam_cycles"}:
        existing_exchange = db.scalar(select(DataExchangeRun).where(
            DataExchangeRun.organization_id == credential.organization_id,
            DataExchangeRun.idempotency_key == scoped_key,
        ))
        if existing_exchange:
            if existing_exchange.request_hash != request_hash:
                raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency-Key was already used with different content")
            return _exchange_result_payload(db, existing_exchange, replayed=True)
        try:
            if resource == "assessment_marks":
                exchange_run = _stage_dynamic_assessment_push(
                    db, credential, body.records,
                    scoped_key=scoped_key, request_hash=request_hash,
                )
            else:
                exchange_run = ingest_exchange_records(
                    db,
                    organization_id=credential.organization_id,
                    resource_key=resource,
                    records=body.records,
                    source_type="erp_push",
                    idempotency_key=scoped_key,
                    request_hash=request_hash,
                    auto_commit=True,
                )
            log_action(
                db, organization_id=credential.organization_id, user_id=None,
                action=f"college.integration.{resource}_received",
                resource_type="data_exchange_run", resource_id=exchange_run.id,
                rows_affected=exchange_run.committed_count,
                meta={"received": exchange_run.row_count, "failed": exchange_run.invalid_count, "credential_id": credential.id},
            )
            db.commit()
        except (ValueError, PermissionError) as exc:
            db.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        except IntegrityError:
            db.rollback()
            existing_exchange = db.scalar(select(DataExchangeRun).where(
                DataExchangeRun.organization_id == credential.organization_id,
                DataExchangeRun.idempotency_key == scoped_key,
            ))
            if existing_exchange and existing_exchange.request_hash == request_hash:
                return _exchange_result_payload(db, existing_exchange, replayed=True)
            raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency-Key was already used with different content")
        return _exchange_result_payload(db, exchange_run)
    existing = db.execute(select(CollegeImportRun).where(
        CollegeImportRun.credential_id == credential.id,
        CollegeImportRun.idempotency_key == scoped_key,
    )).scalar_one_or_none()
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency-Key was already used with different content")
        return _run_payload(existing, replayed=True)

    try:
        run = stage_rows(
            db,
            organization_id=credential.organization_id,
            user_id=None,
            source_type="erp_push",
            resource_type=resource,
            rows=body.records,
            mapping={},
            connector_id=credential.connector_id,
            credential_id=credential.id,
            idempotency_key=scoped_key,
            request_hash=request_hash,
        )
    except IntegrityError:
        db.rollback()
        existing = db.execute(select(CollegeImportRun).where(
            CollegeImportRun.credential_id == credential.id,
            CollegeImportRun.idempotency_key == scoped_key,
        )).scalar_one_or_none()
        if existing and existing.request_hash == request_hash:
            return _run_payload(existing, replayed=True)
        raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency-Key was already used with different content")
    if run.valid_count:
        commit_run(db, run)
    try:
        log_action(
            db, organization_id=credential.organization_id, user_id=None,
            action="college.integration.records_received", resource_type="college_import_run",
            resource_id=run.id, rows_affected=run.committed_count,
            meta={"resource": resource, "received": run.row_count, "failed": run.failed_count, "credential_id": credential.id},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.execute(select(CollegeImportRun).where(
            CollegeImportRun.credential_id == credential.id,
            CollegeImportRun.idempotency_key == scoped_key,
        )).scalar_one_or_none()
        if existing and existing.request_hash == request_hash:
            return _run_payload(existing, replayed=True)
        raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency-Key was already used with different content")
    db.refresh(run)
    return _run_payload(run)


@integration_router.get("/college/runs/{run_id}")
def integration_run(
    run_id: str,
    credential: CollegeIntegrationCredential = Depends(_require_integration_credential),
    db: Session = Depends(get_db),
):
    _consume_rate_limit(db, credential, 0)
    run = db.execute(select(CollegeImportRun).where(
        CollegeImportRun.id == run_id,
        CollegeImportRun.organization_id == credential.organization_id,
        CollegeImportRun.credential_id == credential.id,
    )).scalar_one_or_none()
    if run:
        return _run_payload(run)
    exchange_run = db.scalar(select(DataExchangeRun).where(
        DataExchangeRun.id == run_id,
        DataExchangeRun.organization_id == credential.organization_id,
        DataExchangeRun.idempotency_key.like(f"push:{credential.id}:%"),
    ))
    if exchange_run:
        return _exchange_result_payload(db, exchange_run)
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Integration run not found")


@integration_router.get("/openapi.json", include_in_schema=False)
def integration_openapi():
    resource_enum = list(RESOURCE_TYPES)
    structure_schemas = {
        "CollegeDepartmentRecord": {
            "type": "object", "additionalProperties": False,
            "required": ["external_id", "name", "code"],
            "properties": {
                "external_id": {"type": "string", "maxLength": 180},
                "name": {"type": "string", "maxLength": 180},
                "code": {"type": "string", "maxLength": 30},
                "description": {"type": ["string", "null"], "maxLength": 1000},
                "source_updated_at": {"type": ["string", "null"], "format": "date-time"},
            },
        },
        "CollegeProgramRecord": {
            "type": "object", "additionalProperties": False,
            "required": ["external_id", "department_code", "name", "code"],
            "properties": {
                "external_id": {"type": "string", "maxLength": 180},
                "department_code": {"type": "string", "maxLength": 30},
                "name": {"type": "string", "maxLength": 200},
                "code": {"type": "string", "maxLength": 40},
                "degree_type": {"type": "string", "enum": ["undergraduate", "postgraduate", "diploma", "certificate"]},
                "duration_semesters": {"type": "integer", "minimum": 1, "maximum": 16},
                "source_updated_at": {"type": ["string", "null"], "format": "date-time"},
            },
        },
        "CollegeCohortRecord": {
            "type": "object", "additionalProperties": False,
            "required": ["external_id", "program_code", "name", "code", "admission_year", "graduation_year"],
            "properties": {
                "external_id": {"type": "string", "maxLength": 180},
                "program_code": {"type": "string", "maxLength": 40},
                "name": {"type": "string", "maxLength": 120},
                "code": {"type": "string", "maxLength": 50},
                "admission_year": {"type": "integer", "minimum": 2000, "maximum": 2200},
                "graduation_year": {"type": "integer", "minimum": 2000, "maximum": 2200},
                "current_semester": {"type": "integer", "minimum": 1, "maximum": 16},
                "section": {"type": ["string", "null"], "maxLength": 20},
                "source_updated_at": {"type": ["string", "null"], "format": "date-time"},
            },
        },
        "CollegeTermRecord": {
            "type": "object", "additionalProperties": False,
            "required": ["external_id", "name", "academic_year", "term_number", "starts_on", "ends_on"],
            "properties": {
                "external_id": {"type": "string", "maxLength": 180},
                "name": {"type": "string", "maxLength": 80},
                "academic_year": {"type": "string", "maxLength": 20},
                "term_number": {"type": "integer", "minimum": 1, "maximum": 16},
                "starts_on": {"type": "string", "format": "date"},
                "ends_on": {"type": "string", "format": "date"},
                "status": {"type": "string", "enum": ["planned", "active", "closed"]},
                "is_current": {"type": "boolean"},
                "source_updated_at": {"type": ["string", "null"], "format": "date-time"},
            },
        },
        "CollegeCourseRecord": {
            "type": "object", "additionalProperties": False,
            "required": ["external_id", "department_code", "name", "code"],
            "properties": {
                "external_id": {"type": "string", "maxLength": 180},
                "department_code": {"type": "string", "maxLength": 30},
                "name": {"type": "string", "maxLength": 200},
                "code": {"type": "string", "maxLength": 40},
                "credits": {"type": "integer", "minimum": 0, "maximum": 30},
                "course_type": {"type": "string", "enum": ["core", "elective", "lab", "project", "audit"]},
                "source_updated_at": {"type": ["string", "null"], "format": "date-time"},
            },
        },
        "CollegeAssessmentMarksRecord": {
            "type": "object",
            "additionalProperties": False,
            "required": ["scheme_code", "scheme_version", "cycle_code", "student", "metrics"],
            "properties": {
                "scheme_code": {"type": "string", "maxLength": 50},
                "scheme_version": {"type": "integer", "minimum": 1},
                "cycle_code": {"type": "string", "maxLength": 60},
                "student": {
                    "oneOf": [
                        {"type": "string", "description": "Admission number"},
                        {"type": "object", "required": ["admission_number"], "properties": {"admission_number": {"type": "string"}}, "additionalProperties": False},
                    ],
                },
                "academic_scope": {
                    "type": ["object", "null"],
                    "properties": {
                        "assessment_id": {"type": ["string", "null"], "format": "uuid"},
                        "offering_id": {"type": ["string", "null"], "format": "uuid"},
                    },
                    "additionalProperties": False,
                },
                "metrics": {
                    "type": "object",
                    "description": "Keys and value types come from the selected cycle schema; unknown keys are quarantined.",
                    "additionalProperties": True,
                },
            },
        },
        "CollegeExamCycleRecord": {
            "type": "object",
            "additionalProperties": False,
            "required": ["scheme_code", "scheme_version", "cycle_code", "cycle_name"],
            "properties": {
                "scheme_code": {"type": "string", "maxLength": 50},
                "scheme_version": {"type": "integer", "minimum": 1},
                "component_code": {"type": ["string", "null"], "maxLength": 50},
                "cycle_code": {"type": "string", "maxLength": 60},
                "cycle_name": {"type": "string", "maxLength": 180},
                "term_id": {"type": ["string", "null"], "format": "uuid"},
                "held_on": {"type": ["string", "null"], "format": "date"},
                "due_on": {"type": ["string", "null"], "format": "date"},
                "offering_ids": {
                    "oneOf": [
                        {"type": "array", "items": {"type": "string", "format": "uuid"}},
                        {"type": "string", "description": "Comma-separated IDs"},
                    ],
                },
                "cohort_ids": {
                    "oneOf": [
                        {"type": "array", "items": {"type": "string", "format": "uuid"}},
                        {"type": "string", "description": "Comma-separated IDs"},
                    ],
                },
            },
        },
    }
    structure_schema_refs = {
        "departments": "#/components/schemas/CollegeDepartmentRecord",
        "programs": "#/components/schemas/CollegeProgramRecord",
        "cohorts": "#/components/schemas/CollegeCohortRecord",
        "terms": "#/components/schemas/CollegeTermRecord",
        "courses": "#/components/schemas/CollegeCourseRecord",
        "exam_cycles": "#/components/schemas/CollegeExamCycleRecord",
        "assessment_marks": "#/components/schemas/CollegeAssessmentMarksRecord",
    }
    error_schema = {
        "type": "object",
        "properties": {
            "row": {"type": "integer"},
            "errors": {"type": "array", "items": {"type": "string"}},
        },
    }
    result_schema = {
        "type": "object",
        "required": ["run_id", "resource", "status", "received_count", "committed_count", "failed_count", "errors"],
        "properties": {
            "run_id": {"type": "string", "format": "uuid"},
            "resource": {"type": "string", "enum": resource_enum},
            "status": {"type": "string", "enum": ["invalid", "partial", "committed"]},
            "received_count": {"type": "integer"},
            "committed_count": {"type": "integer"},
            "failed_count": {"type": "integer"},
            "errors": {"type": "array", "items": error_schema},
            "replayed": {"type": "boolean"},
        },
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Edvatiq College ERP Integration API",
            "version": "1.0.0",
            "description": (
                "Organization-scoped, idempotent ingestion for College academic structure and evidence. "
                "Import structure in dependency order: departments, programs, cohorts, terms, courses, "
                "and offerings before exam cycles and dynamic assessment marks. Existing unlinked "
                "codes are quarantined for reviewed linking and missing source rows never delete local data."
            ),
        },
        "paths": {
            "/api/integrations/v1/college/schemas/{resource}": {
                "get": {
                    "summary": "Read the effective schema for a College resource",
                    "description": "For assessment_marks, supply cycle_id or cycle_code to receive the frozen institution-specific metric schema.",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {"name": "resource", "in": "path", "required": True, "schema": {"type": "string", "enum": resource_enum}},
                        {"name": "cycle_id", "in": "query", "required": False, "schema": {"type": "string", "format": "uuid"}},
                        {"name": "cycle_code", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "Effective resource schema"}, "404": {"description": "Resource or cycle not found"}},
                },
            },
            "/api/integrations/v1/college/{resource}": {
                "post": {
                    "summary": "Push a validated College resource batch",
                    "description": "For academic structure resources, use the matching schema in x-edvatiq-resource-schemas and send dependencies first.",
                    "x-edvatiq-resource-schemas": structure_schema_refs,
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {"name": "resource", "in": "path", "required": True, "schema": {"type": "string", "enum": resource_enum}},
                        {"name": "Idempotency-Key", "in": "header", "required": True, "schema": {"type": "string", "minLength": 8, "maxLength": 120}},
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object", "required": ["records"],
                            "properties": {
                                "records": {
                                    "type": "array", "minItems": 1, "maxItems": 500,
                                    "items": {
                                        "type": "object",
                                        "description": "Use the schema referenced for the selected resource. exam_cycles and assessment_marks do not use external_id.",
                                        "properties": {"external_id": {"type": "string", "minLength": 1, "maxLength": 180}},
                                        "additionalProperties": True,
                                    },
                                },
                                "source_cursor": {"type": ["string", "null"]},
                                "sent_at": {"type": ["string", "null"], "format": "date-time"},
                            },
                        }}},
                    },
                    "responses": {
                        "200": {"description": "Batch staged and valid rows committed", "content": {"application/json": {"schema": result_schema}}},
                        "409": {"description": "Idempotency conflict"},
                        "413": {"description": "Body exceeds 2 MB"},
                        "422": {"description": "Request validation failed"},
                        "429": {"description": "Credential rate limit exceeded"},
                    },
                },
            },
            "/api/integrations/v1/college/runs/{run_id}": {
                "get": {
                    "summary": "Read a push run created by this credential",
                    "security": [{"BearerAuth": []}],
                    "parameters": [{"name": "run_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                    "responses": {
                        "200": {"description": "Current run result", "content": {"application/json": {"schema": result_schema}}},
                        "429": {"description": "Credential rate limit exceeded"},
                    },
                },
            },
        },
        "components": {
            "securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}},
            "schemas": structure_schemas,
        },
    }
