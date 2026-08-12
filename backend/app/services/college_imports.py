"""Shared staged import normalization for College CSV and ERP sources."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Client, CollegeAttendanceSnapshot, CollegeCareerEvidence, CollegeClearanceSnapshot, CollegeCohort,
    CollegeExternalRecord, CollegeImportRun, CollegePlacementAssessment,
    CollegeProgram, CollegeStudentProfile, CollegeTermResult,
)


RESOURCE_FIELDS = {
    "students": ("external_id", "admission_number", "first_name", "last_name", "email", "phone", "program_code", "cohort_code", "current_semester"),
    "term_results": ("external_id", "admission_number", "semester", "sgpa", "cgpa", "active_backlogs", "total_backlogs", "credits_earned", "published_on"),
    "attendance": ("external_id", "admission_number", "scope", "classes_held", "classes_attended", "attendance_percent", "as_of"),
    "skills": ("external_id", "admission_number", "title", "proficiency", "verified", "evidence_url"),
    "assessments": ("external_id", "admission_number", "title", "assessment_type", "score_percent", "assessed_on", "provider"),
    "internship_clearance": ("external_id", "admission_number", "status", "as_of", "source_updated_at"),
}


def dotted_get(value, path: str | None):
    if not path:
        return None
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def normalize_row(raw: dict, resource_type: str, mapping: dict) -> dict:
    fields = RESOURCE_FIELDS.get(resource_type)
    if not fields:
        raise ValueError("Unsupported College import resource")
    output = {}
    field_map = mapping.get("fields", mapping)
    value_maps = mapping.get("value_maps", {})
    for field in fields:
        source = field_map.get(field, field)
        value = dotted_get(raw, source) if "." in str(source) else raw.get(source)
        if value is not None and field in value_maps:
            value = value_maps[field].get(str(value), value)
        output[field] = value
    return output


def _decimal(value, field: str, errors: list[str], minimum=0, maximum=100):
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        errors.append(f"{field} must be a number")
        return None
    if number < minimum or number > maximum:
        errors.append(f"{field} must be between {minimum} and {maximum}")
    return float(number)


def _integer(value, field: str, errors: list[str], minimum=0, maximum=100000):
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        errors.append(f"{field} must be a whole number")
        return None
    if number < minimum or number > maximum:
        errors.append(f"{field} must be between {minimum} and {maximum}")
    return number


def _date(value, field: str, errors: list[str]):
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        errors.append(f"{field} must use YYYY-MM-DD")
        return None


def _datetime(value, field: str, errors: list[str]):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"{field} must use ISO 8601 format")
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def validate_row(row: dict, resource_type: str) -> tuple[dict, list[str]]:
    output = dict(row)
    errors = []
    if not str(row.get("admission_number") or "").strip():
        errors.append("admission_number is required")
    if resource_type == "students":
        for field in ("first_name", "program_code", "cohort_code"):
            if not str(row.get(field) or "").strip():
                errors.append(f"{field} is required")
        output["current_semester"] = _integer(row.get("current_semester") or 1, "current_semester", errors, 1, 16)
    elif resource_type == "term_results":
        output["semester"] = _integer(row.get("semester"), "semester", errors, 1, 16)
        if output["semester"] is None:
            errors.append("semester is required")
        output["sgpa"] = _decimal(row.get("sgpa"), "sgpa", errors, 0, 10)
        output["cgpa"] = _decimal(row.get("cgpa"), "cgpa", errors, 0, 10)
        output["active_backlogs"] = _integer(row.get("active_backlogs"), "active_backlogs", errors)
        output["total_backlogs"] = _integer(row.get("total_backlogs"), "total_backlogs", errors)
        output["credits_earned"] = _integer(row.get("credits_earned"), "credits_earned", errors)
        output["published_on"] = _date(row.get("published_on"), "published_on", errors)
    elif resource_type == "attendance":
        output["classes_held"] = _integer(row.get("classes_held") or 0, "classes_held", errors)
        output["classes_attended"] = _integer(row.get("classes_attended") or 0, "classes_attended", errors)
        output["attendance_percent"] = _decimal(row.get("attendance_percent"), "attendance_percent", errors)
        output["as_of"] = _date(row.get("as_of") or date.today(), "as_of", errors)
        if output["classes_attended"] is not None and output["classes_held"] is not None and output["classes_attended"] > output["classes_held"]:
            errors.append("classes_attended cannot exceed classes_held")
    elif resource_type == "skills":
        if not str(row.get("title") or "").strip():
            errors.append("title is required")
        output["verified"] = str(row.get("verified") or "").lower() in {"true", "1", "yes", "verified"}
    elif resource_type == "assessments":
        if not str(row.get("title") or "").strip():
            errors.append("title is required")
        output["score_percent"] = _decimal(row.get("score_percent"), "score_percent", errors)
        output["assessed_on"] = _date(row.get("assessed_on"), "assessed_on", errors)
    elif resource_type == "internship_clearance":
        normalized_status = str(row.get("status") or "").strip().lower()
        if normalized_status not in {"cleared", "pending", "needs_review"}:
            errors.append("status must be cleared, pending, or needs_review")
        output["status"] = normalized_status
        output["as_of"] = _date(row.get("as_of") or date.today(), "as_of", errors)
        output["source_updated_at"] = _datetime(
            row.get("source_updated_at") or datetime.now(timezone.utc),
            "source_updated_at",
            errors,
        )
    return output, errors


def stage_rows(
    db: Session,
    *,
    organization_id: str,
    user_id: str | None,
    source_type: str,
    resource_type: str,
    rows: list[dict],
    mapping: dict,
    connector_id: str | None = None,
    credential_id: str | None = None,
    idempotency_key: str | None = None,
    request_hash: str | None = None,
    allowed_student_ids: set[str] | None = None,
    allowed_program_ids: set[str] | None = None,
    allowed_cohort_ids: set[str] | None = None,
) -> CollegeImportRun:
    if idempotency_key:
        existing = db.execute(select(CollegeImportRun).where(
            CollegeImportRun.organization_id == organization_id,
            CollegeImportRun.idempotency_key == idempotency_key,
        )).scalar_one_or_none()
        if existing:
            return existing
    staged = []
    validation_errors = []
    valid_count = 0
    scoped = allowed_student_ids is not None
    students_by_admission = {
        row.admission_number: row
        for row in db.execute(select(CollegeStudentProfile).where(
            CollegeStudentProfile.organization_id == organization_id,
        )).scalars()
    } if scoped else {}
    programs_by_code = {
        row.code.upper(): row
        for row in db.execute(select(CollegeProgram).where(CollegeProgram.organization_id == organization_id)).scalars()
    } if scoped and resource_type == "students" else {}
    cohorts_by_code = {
        row.code.upper(): row
        for row in db.execute(select(CollegeCohort).where(CollegeCohort.organization_id == organization_id)).scalars()
    } if scoped and resource_type == "students" else {}
    for index, raw in enumerate(rows):
        normalized = normalize_row(raw, resource_type, mapping)
        normalized, errors = validate_row(normalized, resource_type)
        if scoped:
            admission = str(normalized.get("admission_number") or "").strip()
            student = students_by_admission.get(admission)
            if student and student.id not in allowed_student_ids:
                errors.append("student is outside your College access")
            elif resource_type != "students" and not student:
                errors.append("student admission number was not found")
            elif resource_type == "students" and not student:
                program = programs_by_code.get(str(normalized.get("program_code") or "").strip().upper())
                cohort = cohorts_by_code.get(str(normalized.get("cohort_code") or "").strip().upper())
                if program and allowed_program_ids is not None and program.id not in allowed_program_ids:
                    errors.append("program is outside your College access")
                if cohort and allowed_cohort_ids is not None and cohort.id not in allowed_cohort_ids:
                    errors.append("cohort is outside your College access")
        staged.append({"row": index + 1, "data": normalized, "valid": not errors, "errors": errors})
        if errors:
            validation_errors.append({"row": index + 1, "errors": errors})
        else:
            valid_count += 1
    run = CollegeImportRun(
        organization_id=organization_id,
        connector_id=connector_id,
        credential_id=credential_id,
        source_type=source_type,
        resource_type=resource_type,
        status="ready" if valid_count else "invalid",
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        mapping=mapping,
        staged_rows=staged,
        validation_errors=validation_errors,
        row_count=len(rows),
        valid_count=valid_count,
        committed_count=0,
        failed_count=len(rows) - valid_count,
        started_by_user_id=user_id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    return run


def _student(db: Session, organization_id: str, admission_number: str):
    return db.execute(select(CollegeStudentProfile).where(
        CollegeStudentProfile.organization_id == organization_id,
        CollegeStudentProfile.admission_number == admission_number,
    )).scalar_one_or_none()


def _external_link(
    db: Session,
    run: CollegeImportRun,
    row: dict,
    local_type: str,
    local_id: str,
):
    if not run.connector_id or not row.get("external_id"):
        return None
    link = db.execute(select(CollegeExternalRecord).where(
        CollegeExternalRecord.connector_id == run.connector_id,
        CollegeExternalRecord.resource_type == run.resource_type,
        CollegeExternalRecord.external_id == str(row["external_id"]),
    )).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if link:
        link.local_resource_type = local_type
        link.local_resource_id = local_id
        link.last_seen_at = now
    else:
        link = CollegeExternalRecord(
            organization_id=run.organization_id,
            connector_id=run.connector_id,
            resource_type=run.resource_type,
            external_id=str(row["external_id"]),
            local_resource_type=local_type,
            local_resource_id=local_id,
            manual_override_fields=[],
            last_seen_at=now,
        )
        db.add(link)
    if row.get("source_updated_at"):
        source_updated_at = datetime.fromisoformat(str(row["source_updated_at"]).replace("Z", "+00:00"))
        link.source_updated_at = source_updated_at.replace(tzinfo=source_updated_at.tzinfo or timezone.utc)
    link.source_hash = hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return link


def _linked_record(db: Session, run: CollegeImportRun, row: dict, model, local_type: str):
    if not run.connector_id or row.get("external_id") in (None, ""):
        return None, set()
    link = db.execute(select(CollegeExternalRecord).where(
        CollegeExternalRecord.connector_id == run.connector_id,
        CollegeExternalRecord.resource_type == run.resource_type,
        CollegeExternalRecord.external_id == str(row["external_id"]),
    )).scalar_one_or_none()
    if not link or link.local_resource_type != local_type:
        return None, set(link.manual_override_fields or []) if link else set()
    record = db.get(model, link.local_resource_id)
    if not record or record.organization_id != run.organization_id:
        return None, set(link.manual_override_fields or [])
    return record, set(link.manual_override_fields or [])


def _apply_import_values(record, values: dict, manual_overrides: set[str]) -> None:
    for field, value in values.items():
        if field not in manual_overrides:
            setattr(record, field, value)


def commit_run(
    db: Session,
    run: CollegeImportRun,
    *,
    allowed_student_ids: set[str] | None = None,
    allowed_program_ids: set[str] | None = None,
    allowed_cohort_ids: set[str] | None = None,
) -> CollegeImportRun:
    if run.status == "committed":
        return run
    if run.status not in {"ready", "partial"}:
        raise ValueError("Only validated imports can be committed")
    committed = 0
    failures = list(run.validation_errors or [])
    for item in run.staged_rows:
        if not item.get("valid"):
            continue
        row = item["data"]
        savepoint = db.begin_nested()
        try:
            student = _student(db, run.organization_id, str(row["admission_number"]).strip())
            if allowed_student_ids is not None and student and student.id not in allowed_student_ids:
                raise ValueError("Student is outside your College access")
            if run.resource_type == "students":
                linked_student, manual_overrides = _linked_record(
                    db, run, row, CollegeStudentProfile, "college_student_profile",
                )
                if linked_student:
                    student = linked_student
                    if allowed_student_ids is not None and student.id not in allowed_student_ids:
                        raise ValueError("Student is outside your College access")
                program = db.execute(select(CollegeProgram).where(
                    CollegeProgram.organization_id == run.organization_id,
                    CollegeProgram.code == str(row["program_code"]).strip().upper(),
                )).scalar_one_or_none()
                cohort = db.execute(select(CollegeCohort).where(
                    CollegeCohort.organization_id == run.organization_id,
                    CollegeCohort.code == str(row["cohort_code"]).strip().upper(),
                )).scalar_one_or_none()
                if not program or not cohort:
                    raise ValueError("Program or cohort code was not found")
                if allowed_program_ids is not None and program.id not in allowed_program_ids:
                    raise ValueError("Program is outside your College access")
                if allowed_cohort_ids is not None and cohort.id not in allowed_cohort_ids:
                    raise ValueError("Cohort is outside your College access")
                if not student:
                    admission = str(row["admission_number"]).strip()
                    client = Client(
                        organization_id=run.organization_id,
                        client_number=admission,
                        first_name=str(row["first_name"]).strip(),
                        last_name=str(row.get("last_name") or "").strip(),
                        email=str(row.get("email") or "").strip() or None,
                        phone=str(row.get("phone") or "").strip() or None,
                        joined_on=date.today(),
                        status="active",
                    )
                    db.add(client)
                    db.flush()
                    student = CollegeStudentProfile(
                        organization_id=run.organization_id,
                        client_id=client.id,
                        admission_number=admission,
                        program_id=program.id,
                        cohort_id=cohort.id,
                        current_semester=row.get("current_semester") or 1,
                        admitted_on=date.today(),
                        status="active",
                    )
                    db.add(student)
                    db.flush()
                client = db.get(Client, student.client_id)
                if not client:
                    raise ValueError("Student identity was not found")
                _apply_import_values(student, {
                    "admission_number": str(row["admission_number"]).strip(),
                    "program_id": program.id,
                    "cohort_id": cohort.id,
                    "current_semester": row.get("current_semester") or 1,
                }, manual_overrides)
                _apply_import_values(client, {
                    "first_name": str(row["first_name"]).strip(),
                    "last_name": str(row.get("last_name") or "").strip(),
                    "email": str(row.get("email") or "").strip() or None,
                    "phone": str(row.get("phone") or "").strip() or None,
                }, manual_overrides)
                _external_link(db, run, row, "college_student_profile", student.id)
            else:
                if not student:
                    raise ValueError("Student admission number was not found")
                source_key = f"connector:{run.connector_id}" if run.connector_id else run.source_type
                if run.resource_type == "term_results":
                    record, manual_overrides = _linked_record(
                        db, run, row, CollegeTermResult, "college_term_result",
                    )
                    if not record:
                        record = db.execute(select(CollegeTermResult).where(
                            CollegeTermResult.student_profile_id == student.id,
                            CollegeTermResult.semester == row["semester"],
                            CollegeTermResult.source_key == source_key,
                        )).scalar_one_or_none()
                    if not record:
                        record = CollegeTermResult(
                            organization_id=run.organization_id,
                            student_profile_id=student.id,
                            semester=row["semester"],
                            source_type=run.source_type,
                            source_key=source_key,
                        )
                        db.add(record)
                    _apply_import_values(record, {
                        "sgpa": row.get("sgpa"),
                        "cgpa": row.get("cgpa"),
                        "active_backlogs": row.get("active_backlogs"),
                        "total_backlogs": row.get("total_backlogs"),
                        "credits_earned": row.get("credits_earned"),
                        "published_on": date.fromisoformat(row["published_on"]) if row.get("published_on") else None,
                    }, manual_overrides)
                    record.external_id = str(row.get("external_id")) if row.get("external_id") is not None else None
                    db.flush()
                    _external_link(db, run, row, "college_term_result", record.id)
                elif run.resource_type == "attendance":
                    as_of = date.fromisoformat(row["as_of"])
                    scope = str(row.get("scope") or "overall")
                    record, manual_overrides = _linked_record(
                        db, run, row, CollegeAttendanceSnapshot, "college_attendance_snapshot",
                    )
                    if not record:
                        record = db.execute(select(CollegeAttendanceSnapshot).where(
                            CollegeAttendanceSnapshot.student_profile_id == student.id,
                            CollegeAttendanceSnapshot.as_of == as_of,
                            CollegeAttendanceSnapshot.scope_key == scope,
                            CollegeAttendanceSnapshot.source_key == source_key,
                        )).scalar_one_or_none()
                    if not record:
                        record = CollegeAttendanceSnapshot(
                            organization_id=run.organization_id,
                            student_profile_id=student.id,
                            as_of=as_of,
                            scope_key=scope,
                            source_type=run.source_type,
                            source_key=source_key,
                        )
                        db.add(record)
                    _apply_import_values(record, {
                        "classes_held": row.get("classes_held") or 0,
                        "classes_attended": row.get("classes_attended") or 0,
                        "attendance_percent": row.get("attendance_percent"),
                        "as_of": as_of,
                        "scope_key": scope,
                    }, manual_overrides)
                    record.external_id = str(row.get("external_id")) if row.get("external_id") is not None else None
                    db.flush()
                    _external_link(db, run, row, "college_attendance_snapshot", record.id)
                elif run.resource_type == "skills":
                    record, manual_overrides = _linked_record(
                        db, run, row, CollegeCareerEvidence, "college_career_evidence",
                    )
                    external_id = str(row.get("external_id")) if row.get("external_id") is not None else None
                    if not record and external_id:
                        record = db.execute(select(CollegeCareerEvidence).where(
                            CollegeCareerEvidence.organization_id == run.organization_id,
                            CollegeCareerEvidence.student_profile_id == student.id,
                            CollegeCareerEvidence.source_type == run.source_type,
                            CollegeCareerEvidence.external_id == external_id,
                        )).scalar_one_or_none()
                    if not record:
                        record = CollegeCareerEvidence(
                            organization_id=run.organization_id,
                            student_profile_id=student.id,
                            evidence_type="skill",
                            title=str(row["title"]).strip(),
                            source_type=run.source_type,
                        )
                        db.add(record)
                    _apply_import_values(record, {
                        "title": str(row["title"]).strip(),
                        "proficiency": str(row.get("proficiency") or "").strip() or None,
                        "evidence_url": str(row.get("evidence_url") or "").strip() or None,
                        "is_verified": bool(row.get("verified")),
                    }, manual_overrides)
                    record.external_id = external_id
                    db.flush()
                    _external_link(db, run, row, "college_career_evidence", record.id)
                elif run.resource_type == "assessments":
                    record, manual_overrides = _linked_record(
                        db, run, row, CollegePlacementAssessment, "college_placement_assessment",
                    )
                    external_id = str(row.get("external_id")) if row.get("external_id") is not None else None
                    if not record and external_id:
                        record = db.execute(select(CollegePlacementAssessment).where(
                            CollegePlacementAssessment.organization_id == run.organization_id,
                            CollegePlacementAssessment.student_profile_id == student.id,
                            CollegePlacementAssessment.source_type == run.source_type,
                            CollegePlacementAssessment.external_id == external_id,
                        )).scalar_one_or_none()
                    if not record:
                        record = CollegePlacementAssessment(
                            organization_id=run.organization_id,
                            student_profile_id=student.id,
                            assessment_type=str(row.get("assessment_type") or "aptitude"),
                            title=str(row["title"]).strip(),
                            source_type=run.source_type,
                        )
                        db.add(record)
                    _apply_import_values(record, {
                        "assessment_type": str(row.get("assessment_type") or "aptitude"),
                        "title": str(row["title"]).strip(),
                        "score_percent": row.get("score_percent"),
                        "assessed_on": date.fromisoformat(row["assessed_on"]) if row.get("assessed_on") else None,
                        "provider": str(row.get("provider") or "").strip() or None,
                    }, manual_overrides)
                    record.external_id = external_id
                    db.flush()
                    _external_link(db, run, row, "college_placement_assessment", record.id)
                elif run.resource_type == "internship_clearance":
                    as_of = date.fromisoformat(row["as_of"])
                    source_updated_at = datetime.fromisoformat(str(row["source_updated_at"]).replace("Z", "+00:00"))
                    if source_updated_at.tzinfo is None:
                        source_updated_at = source_updated_at.replace(tzinfo=timezone.utc)
                    record, manual_overrides = _linked_record(
                        db, run, row, CollegeClearanceSnapshot, "college_clearance_snapshot",
                    )
                    if not record:
                        record = db.execute(select(CollegeClearanceSnapshot).where(
                            CollegeClearanceSnapshot.student_profile_id == student.id,
                            CollegeClearanceSnapshot.as_of == as_of,
                            CollegeClearanceSnapshot.source_key == source_key,
                        )).scalar_one_or_none()
                    if not record:
                        record = CollegeClearanceSnapshot(
                            organization_id=run.organization_id,
                            student_profile_id=student.id,
                            as_of=as_of,
                            source_type=run.source_type,
                            source_key=source_key,
                            source_updated_at=source_updated_at,
                        )
                        db.add(record)
                    _apply_import_values(record, {
                        "status": row["status"],
                        "as_of": as_of,
                        "source_updated_at": source_updated_at,
                    }, manual_overrides)
                    record.external_id = str(row.get("external_id")) if row.get("external_id") is not None else None
                    db.flush()
                    _external_link(db, run, row, "college_clearance_snapshot", record.id)
            savepoint.commit()
            committed += 1
        except IntegrityError:
            savepoint.rollback()
            failures.append({"row": item.get("row"), "errors": ["Record conflicts with an existing College record"]})
        except (ValueError, TypeError) as exc:
            savepoint.rollback()
            failures.append({"row": item.get("row"), "errors": [str(exc)]})
    run.committed_count = committed
    run.failed_count = len(failures)
    run.validation_errors = failures
    run.status = "committed" if not failures else "partial"
    run.completed_at = datetime.now(timezone.utc)
    db.flush()
    return run
