"""Schema-driven import, export, template, and review APIs."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import Field
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_entitlements, require_permissions
from app.models import DataExchangeArtifact, DataExchangeRow, DataExchangeRun, FeatureFlag, Job, User
from app.schemas.validation import RequestModel
from app.services.audit import log_action
from app.services.college import require_college, tenant_row
from app.services.college_access import CollegeAccess, resolve_college_access
from app.services.cursor_pagination import decode_cursor, encode_cursor, page_response, page_size
from app.services.data_exchange import (
    MAX_EXPORT_ROWS,
    MAX_FILE_BYTES,
    MAX_ROWS,
    RESOURCES,
    RESOURCE_DOMAINS,
    RESOURCE_VIEW_PERMISSIONS,
    RESOURCE_WRITE_PERMISSIONS,
    commit_exchange_run,
    correction_workbook,
    estimate_export_rows,
    generate_export,
    generate_template,
    parse_upload,
    process_import_job,
    resource_catalog,
    resource_schema,
    run_payload,
    stage_exchange_rows,
    store_artifact,
)
from app.services.rbac import get_user_permissions


router = APIRouter(
    prefix="/data-exchange",
    tags=["data-exchange"],
    dependencies=[Depends(require_entitlements("module.college"))],
)


class TemplateBody(RequestModel):
    resource_key: str = Field(min_length=2, max_length=100)
    format: Literal["csv", "xlsx"] = "xlsx"
    mode: Literal["create", "update"] = "create"
    scope: dict = Field(default_factory=dict)


class ExportBody(RequestModel):
    resource_key: str = Field(min_length=2, max_length=100)
    format: Literal["csv", "xlsx"] = "xlsx"
    selection: Literal["selected", "filtered", "all"] = "filtered"
    selected_ids: list[str] = Field(default_factory=list, max_length=5000)
    scope: dict = Field(default_factory=dict)


class CommitBody(RequestModel):
    correction_reason: str | None = Field(default=None, max_length=1000)


def _require_feature(db: Session, organization_id: str) -> None:
    flag = db.scalar(select(FeatureFlag).where(
        FeatureFlag.organization_id == organization_id,
        FeatureFlag.flag == "college.data_exchange_v1",
        FeatureFlag.enabled.is_(True),
    ))
    if not flag:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Data Exchange is not enabled for this College workspace")


def _resource_access(db: Session, user: User, resource_key: str, *, write: bool) -> tuple[set[str], object]:
    resource = RESOURCES.get(resource_key)
    if not resource:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Data exchange resource not found")
    permissions = get_user_permissions(db, user)
    required = RESOURCE_VIEW_PERMISSIONS.get(resource_key)
    if required not in permissions:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This data resource is not available for your role")
    if write and "college.imports.manage" not in permissions:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot import College data")
    write_permission = RESOURCE_WRITE_PERMISSIONS.get(resource_key)
    if write and (not write_permission or write_permission not in permissions):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This import requires the corresponding College work area and safeguard",
        )
    domain = RESOURCE_DOMAINS.get(resource_key, "data")
    data_access = resolve_college_access(db, user, "data")
    domain_access = data_access if domain == "data" else resolve_college_access(db, user, domain)
    constrained = [item for item in (data_access, domain_access) if not item.unrestricted]
    if not constrained:
        access = CollegeAccess(
            unrestricted=True,
            policy_version=max(data_access.policy_version, domain_access.policy_version),
            domain=domain,
        )
    else:
        access = CollegeAccess(
            unrestricted=False,
            student_ids=frozenset.intersection(*(item.student_ids for item in constrained)),
            full_student_ids=frozenset.intersection(*(item.full_student_ids for item in constrained)),
            department_ids=frozenset.intersection(*(item.department_ids for item in constrained)),
            program_ids=frozenset.intersection(*(item.program_ids for item in constrained)),
            cohort_ids=frozenset.intersection(*(item.cohort_ids for item in constrained)),
            course_offering_ids=frozenset.intersection(*(item.course_offering_ids for item in constrained)),
            policy_version=max(data_access.policy_version, domain_access.policy_version),
            domain=domain,
        )
    if write and resource_key in {"academic_structure", "departments", "terms", "assessment_schemes"} and not access.unrestricted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This structure resource requires whole-institution College access")
    return permissions, access


def _parse_scope(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "scope must be valid JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "scope must be an object")
    return value


def _new_run(
    *,
    user: User,
    resource_key: str,
    operation: str,
    source_type: str,
    file_format: str | None,
    scope: dict,
    idempotency_key: str,
    request_hash: str,
    source_filename: str | None = None,
    mapping: dict | None = None,
) -> DataExchangeRun:
    return DataExchangeRun(
        organization_id=user.organization_id,
        resource_key=resource_key,
        operation=operation,
        source_type=source_type,
        file_format=file_format,
        scope=scope,
        mapping=mapping or {},
        source_filename=source_filename,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        initiated_by_user_id=user.id,
        started_at=datetime.now(timezone.utc),
    )


def _access_mapping(access) -> dict:
    return {
        "allowed_student_ids": None if access.unrestricted else list(access.student_ids),
        "allowed_department_ids": None if access.unrestricted else list(access.department_ids),
        "allowed_program_ids": None if access.unrestricted else list(access.program_ids),
        "allowed_cohort_ids": None if access.unrestricted else list(access.cohort_ids),
        "allowed_course_offering_ids": None if access.unrestricted else list(access.course_offering_ids),
        "policy_version": access.policy_version,
    }


def _ensure_run_visible(run: DataExchangeRun, access: CollegeAccess, user: User) -> None:
    if not access.unrestricted and run.initiated_by_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Data exchange run not found")
    stored_policy_version = (run.mapping or {}).get("policy_version")
    if stored_policy_version is not None and int(stored_policy_version) != access.policy_version:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Data exchange run not found",
        )


@router.get("/resources")
def list_resources(
    user: User = Depends(require_permissions("college.data.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    _require_feature(db, user.organization_id)
    resolve_college_access(db, user, "data")
    permissions = get_user_permissions(db, user)
    return {"items": resource_catalog(permissions), "feature": "college.data_exchange_v1"}


@router.get("/resources/{resource_key}/schema")
def get_resource_schema(
    resource_key: str,
    cycle_id: str | None = None,
    user: User = Depends(require_permissions("college.data.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    _require_feature(db, user.organization_id)
    _permissions, access = _resource_access(db, user, resource_key, write=False)
    scope = _access_mapping(access)
    if cycle_id:
        scope["cycle_id"] = cycle_id
    return resource_schema(db, user.organization_id, resource_key, scope)


@router.post("/templates", status_code=201)
def create_template(
    body: TemplateBody,
    user: User = Depends(require_permissions("college.imports.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    _require_feature(db, user.organization_id)
    _permissions, access = _resource_access(db, user, body.resource_key, write=True)
    resource = RESOURCES[body.resource_key]
    if body.format == "csv" and "csv" not in resource.methods:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "CSV is not available for this resource")
    if body.format == "xlsx" and "excel" not in resource.methods:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Excel is not available for this resource")
    if body.mode == "update" and not resource.update_supported:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This resource does not provide update templates")
    digest = hashlib.sha256(json.dumps(body.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    authorized_scope = {**body.scope, **_access_mapping(access)}
    run = _new_run(
        user=user, resource_key=body.resource_key, operation="template", source_type="generated",
        file_format=body.format, scope=authorized_scope, mapping=_access_mapping(access),
        idempotency_key=f"template:{uuid.uuid4()}", request_hash=digest,
    )
    db.add(run)
    db.flush()
    content, filename, content_type = generate_template(
        db, user.organization_id, body.resource_key,
        file_format=body.format, mode=body.mode, scope=authorized_scope,
    )
    store_artifact(db, run, kind="template", filename=filename, content_type=content_type, content=content)
    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    log_action(
        db, organization_id=user.organization_id, user_id=user.id,
        action="data_exchange.template.create", resource_type="data_exchange_run", resource_id=run.id,
        permission="college.imports.manage", meta={"resource_key": body.resource_key, "mode": body.mode},
    )
    db.commit()
    return run_payload(run)


@router.post("/imports", status_code=201)
async def create_import(
    file: UploadFile = File(...),
    resource_key: str = Form(...),
    idempotency_key: str = Form(..., min_length=8, max_length=180),
    scope: str | None = Form(None),
    correction_reason: str | None = Form(None, max_length=1000),
    user: User = Depends(require_permissions("college.imports.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    _require_feature(db, user.organization_id)
    _permissions, access = _resource_access(db, user, resource_key, write=True)
    resource = RESOURCES[resource_key]
    filename = (file.filename or "upload").strip()[:255]
    file_format = "csv" if filename.casefold().endswith(".csv") else "xlsx"
    expected_method = "csv" if file_format == "csv" else "excel"
    if expected_method not in resource.methods:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{expected_method.upper()} import is not available for this resource")
    content = await file.read(MAX_FILE_BYTES + 1)
    request_hash = hashlib.sha256(content).hexdigest()
    existing = db.scalar(select(DataExchangeRun).where(
        DataExchangeRun.organization_id == user.organization_id,
        DataExchangeRun.idempotency_key == idempotency_key,
    ))
    if existing:
        if existing.request_hash != request_hash or existing.resource_key != resource_key:
            raise HTTPException(status.HTTP_409_CONFLICT, "This idempotency key was already used for different content")
        return run_payload(existing)
    parsed_scope = _parse_scope(scope)
    rows, metadata = parse_upload(content, filename)
    metadata_resource = str(metadata.get("resource_key") or "")
    if metadata_resource and metadata_resource != resource_key:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The workbook belongs to a different data resource")
    metadata_scope = metadata.get("scope")
    if metadata_scope and not parsed_scope:
        try:
            parsed_scope = json.loads(metadata_scope)
        except (TypeError, json.JSONDecodeError):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The workbook scope metadata is invalid")
    run = _new_run(
        user=user, resource_key=resource_key, operation="import", source_type=file_format,
        file_format=file_format, scope=parsed_scope, idempotency_key=idempotency_key,
        request_hash=request_hash, source_filename=filename, mapping=_access_mapping(access),
    )
    run.correction_reason = correction_reason
    db.add(run)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This import request was already submitted") from exc
    store_artifact(db, run, kind="source", filename=filename, content_type=file.content_type or "application/octet-stream", content=content)
    if len(rows) > 1000:
        run.status = "queued"
        db.add(Job(
            organization_id=user.organization_id,
            kind="data_exchange_validate",
            payload={"run_id": run.id},
            status="queued",
            run_at=datetime.now(timezone.utc),
            max_attempts=3,
            idempotency_key=f"data-exchange-validate:{run.id}"[:120],
        ))
    else:
        stage_exchange_rows(db, run, rows)
        invalid = list(db.scalars(select(DataExchangeRow).where(
            DataExchangeRow.run_id == run.id,
            DataExchangeRow.status.in_(("invalid", "conflict")),
        ).order_by(DataExchangeRow.row_number)))
        if invalid:
            correction_content = correction_workbook(run, invalid)
            store_artifact(
                db, run, kind="corrections", filename=f"{resource_key}-corrections.xlsx",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                content=correction_content,
            )
    log_action(
        db, organization_id=user.organization_id, user_id=user.id,
        action="data_exchange.import.preview", resource_type="data_exchange_run", resource_id=run.id,
        permission="college.imports.manage", rows_affected=len(rows),
        meta={"resource_key": resource_key, "queued": len(rows) > 1000},
    )
    db.commit()
    return run_payload(run)


@router.post("/exports", status_code=201)
def create_export(
    body: ExportBody,
    user: User = Depends(require_permissions("college.data.view", "college.data.export")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    _require_feature(db, user.organization_id)
    _permissions, access = _resource_access(db, user, body.resource_key, write=False)
    if not access.unrestricted and body.resource_key in {"academic_structure", "audits"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This export requires whole-institution access")
    if not RESOURCES[body.resource_key].exportable:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This resource cannot be exported")
    if body.selection == "selected" and not body.selected_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Select at least one record to export")
    if body.selection == "selected" and body.resource_key == "academic_structure":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Academic structure is exported as a dependency-ordered package; use current filters or all records",
        )
    scope = {
        **body.scope,
        **_access_mapping(access),
        "selection": body.selection,
        "selected_ids": body.selected_ids,
    }
    digest = hashlib.sha256(json.dumps(body.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    run = _new_run(
        user=user, resource_key=body.resource_key, operation="export", source_type="generated",
        file_format=body.format, scope=scope, mapping=_access_mapping(access),
        idempotency_key=f"export:{uuid.uuid4()}", request_hash=digest,
    )
    db.add(run)
    db.flush()
    estimated_count = estimate_export_rows(db, user.organization_id, body.resource_key, scope)
    if estimated_count > MAX_ROWS:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "This export exceeds 10,000 rows. Narrow the current filters before exporting.",
        )
    run.row_count = estimated_count
    if estimated_count > MAX_EXPORT_ROWS:
        run.status = "queued"
        db.add(Job(
            organization_id=user.organization_id,
            kind="data_exchange_export",
            payload={"run_id": run.id},
            status="queued",
            run_at=datetime.now(timezone.utc),
            max_attempts=3,
            idempotency_key=f"data-exchange-export:{run.id}"[:120],
        ))
        row_count = estimated_count
    else:
        content, filename, content_type, row_count = generate_export(
            db, user.organization_id, body.resource_key, file_format=body.format, scope=scope,
        )
        store_artifact(db, run, kind="export", filename=filename, content_type=content_type, content=content)
        run.row_count = row_count
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
    log_action(
        db, organization_id=user.organization_id, user_id=user.id,
        action="data_exchange.export.create", resource_type="data_exchange_run", resource_id=run.id,
        permission="college.data.export", rows_affected=row_count,
        meta={"resource_key": body.resource_key, "selection": body.selection, "queued": run.status == "queued"},
    )
    db.commit()
    return run_payload(run)


@router.get("/runs")
def list_runs(
    operation: Literal["template", "import", "export"] | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_permissions("college.data.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    _require_feature(db, user.organization_id)
    access = resolve_college_access(db, user, "data")
    permissions = get_user_permissions(db, user)
    visible_resource_keys = {row["key"] for row in resource_catalog(permissions)}
    if not visible_resource_keys:
        return page_response([], None)
    filters = {"operation": operation}
    values = decode_cursor(cursor, scope="data-exchange.runs", organization_id=user.organization_id, filters=filters)
    statement = select(DataExchangeRun).where(
        DataExchangeRun.organization_id == user.organization_id,
        DataExchangeRun.resource_key.in_(visible_resource_keys),
    )
    if "college.data.export" not in permissions:
        statement = statement.where(DataExchangeRun.operation != "export")
    if not access.unrestricted:
        statement = statement.where(
            DataExchangeRun.initiated_by_user_id == user.id,
            DataExchangeRun.mapping["policy_version"].as_integer() == access.policy_version,
        )
    if operation:
        statement = statement.where(DataExchangeRun.operation == operation)
    if values:
        at = datetime.fromisoformat(str(values["at"]))
        statement = statement.where(or_(
            DataExchangeRun.created_at < at,
            and_(DataExchangeRun.created_at == at, DataExchangeRun.id < str(values["id"])),
        ))
    size = page_size(limit)
    rows = list(db.scalars(statement.order_by(DataExchangeRun.created_at.desc(), DataExchangeRun.id.desc()).limit(size + 1)))
    has_more = len(rows) > size
    rows = rows[:size]
    next_cursor = encode_cursor(
        scope="data-exchange.runs", organization_id=user.organization_id, filters=filters,
        values={"at": rows[-1].created_at.isoformat(), "id": rows[-1].id},
    ) if has_more and rows else None
    return page_response([run_payload(row) for row in rows], next_cursor)


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    user: User = Depends(require_permissions("college.data.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    _require_feature(db, user.organization_id)
    run = tenant_row(db, DataExchangeRun, run_id, user, "Data exchange run")
    _permissions, access = _resource_access(db, user, run.resource_key, write=False)
    _ensure_run_visible(run, access, user)
    if run.operation == "export" and "college.data.export" not in _permissions:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Export access is required")
    return run_payload(run)


@router.get("/runs/{run_id}/rows")
def run_rows(
    run_id: str,
    row_status: Literal["all", "valid", "invalid", "conflict", "committed"] = Query("all", alias="status"),
    cursor: int | None = Query(default=None, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(require_permissions("college.data.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    _require_feature(db, user.organization_id)
    run = tenant_row(db, DataExchangeRun, run_id, user, "Data exchange run")
    _permissions, access = _resource_access(
        db, user, run.resource_key, write=run.operation == "import",
    )
    _ensure_run_visible(run, access, user)
    statement = select(DataExchangeRow).where(
        DataExchangeRow.organization_id == user.organization_id,
        DataExchangeRow.run_id == run.id,
    )
    if row_status != "all":
        statement = statement.where(DataExchangeRow.status == row_status)
    if cursor is not None:
        statement = statement.where(DataExchangeRow.row_number > cursor)
    size = page_size(limit, default=50)
    rows = list(db.scalars(statement.order_by(DataExchangeRow.row_number, DataExchangeRow.id).limit(size + 1)))
    has_more = len(rows) > size
    rows = rows[:size]
    return {
        "items": [{
            "id": row.id, "row_number": row.row_number, "action": row.action,
            "status": row.status, "record_id": row.record_id, "values": row.values,
            "changes": row.changes, "errors": row.errors, "warnings": row.warnings,
        } for row in rows],
        "next_cursor": rows[-1].row_number if has_more and rows else None,
        "has_more": has_more,
        "run": run_payload(run),
    }


@router.post("/runs/{run_id}/commit")
def commit_run(
    run_id: str,
    body: CommitBody,
    user: User = Depends(require_permissions("college.imports.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    _require_feature(db, user.organization_id)
    run = tenant_row(db, DataExchangeRun, run_id, user, "Data exchange run")
    permissions, access = _resource_access(db, user, run.resource_key, write=True)
    _ensure_run_visible(run, access, user)
    if body.correction_reason:
        run.correction_reason = body.correction_reason
    try:
        commit_exchange_run(
            db, run, user_id=user.id,
            can_correct="college.assessments.correct" in permissions,
        )
        log_action(
            db, organization_id=user.organization_id, user_id=user.id,
            action="data_exchange.import.commit", resource_type="data_exchange_run", resource_id=run.id,
            permission="college.imports.manage", rows_affected=run.committed_count,
            meta={"resource_key": run.resource_key, "has_correction_reason": bool(run.correction_reason)},
        )
        db.commit()
    except PermissionError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except (IntegrityError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return run_payload(run)


@router.post("/runs/{run_id}/cancel")
def cancel_run(
    run_id: str,
    user: User = Depends(require_permissions("college.imports.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    _require_feature(db, user.organization_id)
    run = tenant_row(db, DataExchangeRun, run_id, user, "Data exchange run")
    _permissions, access = _resource_access(db, user, run.resource_key, write=True)
    _ensure_run_visible(run, access, user)
    if run.status in {"committed", "completed", "cancelled"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "This run can no longer be cancelled")
    run.status = "cancelled"
    run.completed_at = datetime.now(timezone.utc)
    log_action(
        db, organization_id=user.organization_id, user_id=user.id,
        action="data_exchange.run.cancel", resource_type="data_exchange_run", resource_id=run.id,
        permission="college.imports.manage", meta={"resource_key": run.resource_key},
    )
    db.commit()
    return run_payload(run)


@router.get("/runs/{run_id}/artifacts/{kind}")
def download_artifact(
    run_id: str,
    kind: Literal["template", "source", "export", "corrections"],
    user: User = Depends(require_permissions("college.data.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    _require_feature(db, user.organization_id)
    run = tenant_row(db, DataExchangeRun, run_id, user, "Data exchange run")
    protected_source = kind in {"template", "source", "corrections"}
    _permissions, access = _resource_access(db, user, run.resource_key, write=protected_source)
    _ensure_run_visible(run, access, user)
    artifact_policy_version = (run.mapping or {}).get("policy_version")
    if artifact_policy_version is not None and int(artifact_policy_version) != access.policy_version:
        raise HTTPException(status.HTTP_409_CONFLICT, "Your access changed after this file was generated. Generate a new file")
    if kind == "export" and "college.data.export" not in get_user_permissions(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Export access is required")
    artifact = db.scalar(select(DataExchangeArtifact).where(
        DataExchangeArtifact.organization_id == user.organization_id,
        DataExchangeArtifact.run_id == run.id,
        DataExchangeArtifact.kind == kind,
    ))
    if not artifact:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    safe_filename = artifact.filename.replace('"', "")
    return Response(
        content=artifact.content,
        media_type=artifact.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
            "Content-Length": str(artifact.byte_size),
            "X-Content-SHA256": artifact.checksum,
        },
    )
