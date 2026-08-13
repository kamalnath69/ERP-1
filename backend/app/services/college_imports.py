"""Shared staged import normalization for College CSV and ERP sources."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Client, CollegeAttendanceSnapshot, CollegeCareerEvidence, CollegeClearanceSnapshot, CollegeCohort,
    CollegeCourse, CollegeDepartment, CollegeExternalRecord, CollegeImportRun,
    CollegePlacementAssessment, CollegeProgram, CollegeStudentProfile, CollegeTerm,
    CollegeTermResult,
)


RESOURCE_FIELDS = {
    "departments": ("external_id", "name", "code", "description", "source_updated_at"),
    "programs": ("external_id", "department_code", "name", "code", "degree_type", "duration_semesters", "source_updated_at"),
    "terms": ("external_id", "name", "academic_year", "term_number", "starts_on", "ends_on", "status", "is_current", "source_updated_at"),
    "cohorts": ("external_id", "program_code", "name", "code", "admission_year", "graduation_year", "current_semester", "section", "source_updated_at"),
    "courses": ("external_id", "department_code", "name", "code", "credits", "course_type", "source_updated_at"),
    "students": ("external_id", "admission_number", "first_name", "last_name", "email", "phone", "program_code", "cohort_code", "current_semester"),
    "term_results": ("external_id", "admission_number", "semester", "sgpa", "cgpa", "active_backlogs", "total_backlogs", "credits_earned", "published_on"),
    "attendance": ("external_id", "admission_number", "scope", "classes_held", "classes_attended", "attendance_percent", "as_of"),
    "skills": ("external_id", "admission_number", "title", "proficiency", "verified", "evidence_url"),
    "assessments": ("external_id", "admission_number", "title", "assessment_type", "score_percent", "assessed_on", "provider"),
    "internship_clearance": ("external_id", "admission_number", "status", "as_of", "source_updated_at"),
}

STRUCTURE_RESOURCES = frozenset({"departments", "programs", "terms", "cohorts", "courses"})
STUDENT_RESOURCES = frozenset({
    "students", "term_results", "attendance", "skills", "assessments",
    "internship_clearance",
})

STRUCTURE_MODELS = {
    "departments": (CollegeDepartment, "college_department"),
    "programs": (CollegeProgram, "college_program"),
    "terms": (CollegeTerm, "college_term"),
    "cohorts": (CollegeCohort, "college_cohort"),
    "courses": (CollegeCourse, "college_course"),
}

MANUAL_UPDATE_MODELS = {
    "students": CollegeStudentProfile,
    "term_results": CollegeTermResult,
    "attendance": CollegeAttendanceSnapshot,
    "skills": CollegeCareerEvidence,
}
MANUAL_CLEARABLE_FIELDS = {
    "students": {"last_name", "email", "phone"},
    "term_results": {"sgpa", "cgpa", "active_backlogs", "total_backlogs", "credits_earned", "published_on"},
    "attendance": {"attendance_percent"},
    "skills": {"external_id", "proficiency", "evidence_url"},
}
CLEAR_SENTINEL = "__CLEAR__"


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
        parsed = Decimal(str(value))
        if not parsed.is_finite() or parsed != parsed.to_integral_value():
            raise ValueError
        number = int(parsed)
    except (InvalidOperation, TypeError, ValueError):
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
    except (TypeError, ValueError):
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
        except (TypeError, ValueError):
            errors.append(f"{field} must use ISO 8601 format")
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _optional_text(value):
    normalized = str(value or "").strip()
    return normalized or None


def _normalized_code(value) -> str:
    return " ".join(str(value or "").strip().upper().split()).replace(" ", "-")


def _normalized_section(value) -> str:
    return " ".join(str(value or "").strip().upper().split()) or "GENERAL"


def _required_text(row: dict, output: dict, errors: list[str], *fields: str) -> None:
    for field in fields:
        normalized = str(row.get(field) or "").strip()
        if not normalized:
            errors.append(f"{field} is required")
        output[field] = normalized


def _boolean(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y", "active"}


def _optional_source_time(row: dict, errors: list[str]):
    value = row.get("source_updated_at")
    return _datetime(value, "source_updated_at", errors) if value not in (None, "") else None


def validate_row(row: dict, resource_type: str) -> tuple[dict, list[str]]:
    output = dict(row)
    errors = []
    if resource_type in STUDENT_RESOURCES and not str(row.get("admission_number") or "").strip():
        errors.append("admission_number is required")
    if resource_type == "departments":
        _required_text(row, output, errors, "name", "code")
        output["code"] = _normalized_code(row.get("code"))
        output["description"] = _optional_text(row.get("description"))
        output["source_updated_at"] = _optional_source_time(row, errors)
    elif resource_type == "programs":
        _required_text(row, output, errors, "department_code", "name", "code")
        output["department_code"] = _normalized_code(row.get("department_code"))
        output["code"] = _normalized_code(row.get("code"))
        degree_type = str(row.get("degree_type") or "undergraduate").strip().lower()
        if degree_type not in {"undergraduate", "postgraduate", "diploma", "certificate"}:
            errors.append("degree_type must be undergraduate, postgraduate, diploma, or certificate")
        output["degree_type"] = degree_type
        output["duration_semesters"] = _integer(
            row.get("duration_semesters") or 6, "duration_semesters", errors, 1, 16,
        )
        output["source_updated_at"] = _optional_source_time(row, errors)
    elif resource_type == "terms":
        _required_text(row, output, errors, "name", "academic_year")
        output["term_number"] = _integer(row.get("term_number"), "term_number", errors, 1, 16)
        if output["term_number"] is None:
            errors.append("term_number is required")
        output["starts_on"] = _date(row.get("starts_on"), "starts_on", errors)
        output["ends_on"] = _date(row.get("ends_on"), "ends_on", errors)
        if not output["starts_on"]:
            errors.append("starts_on is required")
        if not output["ends_on"]:
            errors.append("ends_on is required")
        if output["starts_on"] and output["ends_on"] and output["ends_on"] <= output["starts_on"]:
            errors.append("ends_on must be after starts_on")
        term_status = str(row.get("status") or "planned").strip().lower()
        if term_status not in {"planned", "active", "closed"}:
            errors.append("status must be planned, active, or closed")
        output["status"] = term_status
        output["is_current"] = _boolean(row.get("is_current"))
        output["source_updated_at"] = _optional_source_time(row, errors)
    elif resource_type == "cohorts":
        _required_text(row, output, errors, "program_code", "name", "code")
        output["program_code"] = _normalized_code(row.get("program_code"))
        output["code"] = _normalized_code(row.get("code"))
        output["admission_year"] = _integer(row.get("admission_year"), "admission_year", errors, 2000, 2200)
        output["graduation_year"] = _integer(row.get("graduation_year"), "graduation_year", errors, 2000, 2200)
        if output["admission_year"] is None:
            errors.append("admission_year is required")
        if output["graduation_year"] is None:
            errors.append("graduation_year is required")
        if (
            output["admission_year"] is not None
            and output["graduation_year"] is not None
            and output["graduation_year"] < output["admission_year"]
        ):
            errors.append("graduation_year cannot be before admission_year")
        output["current_semester"] = _integer(
            row.get("current_semester") or 1, "current_semester", errors, 1, 16,
        )
        output["section"] = _normalized_section(row.get("section"))
        output["source_updated_at"] = _optional_source_time(row, errors)
    elif resource_type == "courses":
        _required_text(row, output, errors, "department_code", "name", "code")
        output["department_code"] = _normalized_code(row.get("department_code"))
        output["code"] = _normalized_code(row.get("code"))
        output["credits"] = _integer(row.get("credits") if row.get("credits") not in (None, "") else 3, "credits", errors, 0, 30)
        course_type = str(row.get("course_type") or "core").strip().lower()
        if course_type not in {"core", "elective", "lab", "project", "audit"}:
            errors.append("course_type must be core, elective, lab, project, or audit")
        output["course_type"] = course_type
        output["source_updated_at"] = _optional_source_time(row, errors)
    elif resource_type == "students":
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


def _manual_file_identity(
    db: Session,
    organization_id: str,
    resource_type: str,
    row: dict,
    errors: list[str],
) -> None:
    """Require stable IDs for file updates and reject natural-key overwrites."""
    if resource_type not in MANUAL_UPDATE_MODELS:
        return
    record_id = str(row.get("record_id") or "").strip() or None
    version = _integer(row.get("version"), "version", errors, 1, 1_000_000) if row.get("version") not in (None, "") else None
    student = _student(db, organization_id, str(row.get("admission_number") or "").strip())
    model = MANUAL_UPDATE_MODELS[resource_type]
    record = db.get(model, record_id) if record_id else None
    if record_id:
        if not record or record.organization_id != organization_id:
            errors.append("record_id was not found in this college")
            return
        if version is None:
            errors.append("version is required for updates")
        elif version != record.version:
            errors.append("record version is stale; download a new update template")
        if resource_type == "students":
            if record.admission_number != str(row.get("admission_number") or "").strip():
                errors.append("admission_number cannot identify a different student than record_id")
        elif not student or record.student_profile_id != student.id:
            errors.append("admission_number does not match record_id")
        row["_manual_action"] = "update"
        row["_record_id"] = record.id
        row["_record_version"] = version
        return
    if version is not None:
        errors.append("record_id is required when version is supplied")

    duplicate = None
    if resource_type == "students":
        duplicate = student
    elif student and resource_type == "term_results" and row.get("semester") is not None:
        duplicate = db.scalar(select(CollegeTermResult.id).where(
            CollegeTermResult.organization_id == organization_id,
            CollegeTermResult.student_profile_id == student.id,
            CollegeTermResult.semester == row["semester"],
        ).limit(1))
    elif student and resource_type == "attendance" and row.get("as_of"):
        duplicate = db.scalar(select(CollegeAttendanceSnapshot.id).where(
            CollegeAttendanceSnapshot.organization_id == organization_id,
            CollegeAttendanceSnapshot.student_profile_id == student.id,
            CollegeAttendanceSnapshot.as_of == date.fromisoformat(str(row["as_of"])[:10]),
            CollegeAttendanceSnapshot.scope_key == str(row.get("scope") or "overall"),
        ).limit(1))
    elif student and resource_type == "skills" and str(row.get("title") or "").strip():
        duplicate = db.scalar(select(CollegeCareerEvidence.id).where(
            CollegeCareerEvidence.organization_id == organization_id,
            CollegeCareerEvidence.student_profile_id == student.id,
            CollegeCareerEvidence.evidence_type == "skill",
            func.lower(CollegeCareerEvidence.title) == str(row["title"]).strip().casefold(),
        ).limit(1))
    if duplicate:
        errors.append("A matching record already exists; use a prefilled update template with record_id and version")
    row["_manual_action"] = "create"


def _hydrate_manual_update_blanks(
    db: Session,
    organization_id: str,
    resource_type: str,
    row: dict,
    errors: list[str],
) -> None:
    record_id = str(row.get("record_id") or "").strip()
    model = MANUAL_UPDATE_MODELS.get(resource_type)
    if not record_id or not model:
        return
    record = db.get(model, record_id)
    if not record or record.organization_id != organization_id:
        return
    if resource_type == "students":
        client = db.get(Client, record.client_id)
        program = db.get(CollegeProgram, record.program_id)
        cohort = db.get(CollegeCohort, record.cohort_id)
        current = {
            "admission_number": record.admission_number,
            "first_name": client.first_name if client else None,
            "last_name": client.last_name if client else None,
            "email": client.email if client else None,
            "phone": client.phone if client else None,
            "program_code": program.code if program else None,
            "cohort_code": cohort.code if cohort else None,
            "current_semester": record.current_semester,
        }
    else:
        student = db.get(CollegeStudentProfile, record.student_profile_id)
        current = {"admission_number": student.admission_number if student else None}
        if resource_type == "term_results":
            current.update({
                "external_id": record.external_id, "semester": record.semester,
                "sgpa": record.sgpa, "cgpa": record.cgpa,
                "active_backlogs": record.active_backlogs, "total_backlogs": record.total_backlogs,
                "credits_earned": record.credits_earned, "published_on": record.published_on,
            })
        elif resource_type == "attendance":
            current.update({
                "external_id": record.external_id, "scope": record.scope_key,
                "classes_held": record.classes_held, "classes_attended": record.classes_attended,
                "attendance_percent": record.attendance_percent, "as_of": record.as_of,
            })
        else:
            current.update({
                "external_id": record.external_id, "title": record.title,
                "proficiency": record.proficiency, "verified": record.is_verified,
                "evidence_url": record.evidence_url,
            })
    clearable = MANUAL_CLEARABLE_FIELDS.get(resource_type, set())
    for field in RESOURCE_FIELDS[resource_type]:
        incoming = row.get(field)
        if incoming == CLEAR_SENTINEL:
            if field not in clearable:
                errors.append(f"{field} cannot be cleared")
            else:
                row[field] = None
        elif incoming in (None, ""):
            row[field] = current.get(field)


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
        prevalidation_errors: list[str] = []
        if source_type in {"csv", "xlsx"}:
            normalized["record_id"] = raw.get("record_id")
            normalized["version"] = raw.get("version")
            _hydrate_manual_update_blanks(
                db, organization_id, resource_type, normalized, prevalidation_errors,
            )
        normalized, errors = validate_row(normalized, resource_type)
        errors = [*prevalidation_errors, *errors]
        if source_type in {"csv", "xlsx"}:
            _manual_file_identity(db, organization_id, resource_type, normalized, errors)
        if scoped and resource_type in STRUCTURE_RESOURCES:
            errors.append("Academic structure imports require organization-wide College access")
        elif scoped:
            admission = str(normalized.get("admission_number") or "").strip()
            student = students_by_admission.get(admission)
            if student and student.id not in allowed_student_ids:
                errors.append("student is outside your College access")
            elif resource_type != "students" and not student:
                errors.append("student admission number was not found")
            elif resource_type == "students" and not student:
                program = programs_by_code.get(_normalized_code(normalized.get("program_code")))
                cohort = cohorts_by_code.get(_normalized_code(normalized.get("cohort_code")))
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


def _reject_stale_structure_update(db: Session, run: CollegeImportRun, row: dict) -> None:
    """Keep the latest accepted ERP structure snapshot authoritative."""
    if not run.connector_id or row.get("external_id") in (None, "") or not row.get("source_updated_at"):
        return
    link = db.execute(select(CollegeExternalRecord).where(
        CollegeExternalRecord.connector_id == run.connector_id,
        CollegeExternalRecord.resource_type == run.resource_type,
        CollegeExternalRecord.external_id == str(row["external_id"]),
    )).scalar_one_or_none()
    if not link or not link.source_updated_at:
        return
    incoming = datetime.fromisoformat(str(row["source_updated_at"]).replace("Z", "+00:00"))
    incoming = incoming.replace(tzinfo=incoming.tzinfo or timezone.utc)
    current = link.source_updated_at.replace(tzinfo=link.source_updated_at.tzinfo or timezone.utc)
    if incoming < current:
        raise ValueError("source_updated_at is older than the latest accepted ERP structure snapshot")
    incoming_hash = hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    if incoming == current and link.source_hash and link.source_hash != incoming_hash:
        raise ValueError("ERP structure content changed without a newer source_updated_at value")


def _apply_import_values(record, values: dict, manual_overrides: set[str]) -> bool:
    changed = False
    for field, value in values.items():
        if field not in manual_overrides and getattr(record, field, None) != value:
            setattr(record, field, value)
            changed = True
    return changed


def _record_by_code(db: Session, model, organization_id: str, code: str):
    return db.execute(select(model).where(
        model.organization_id == organization_id,
        func.upper(model.code) == _normalized_code(code),
    )).scalar_one_or_none()


def _unlinked_structure_collision(db: Session, run: CollegeImportRun, row: dict, model):
    if run.resource_type == "terms":
        return db.execute(select(CollegeTerm).where(
            CollegeTerm.organization_id == run.organization_id,
            CollegeTerm.academic_year == row["academic_year"],
            CollegeTerm.term_number == row["term_number"],
        )).scalar_one_or_none()
    return _record_by_code(db, model, run.organization_id, row["code"])


def _active_parent(db: Session, model, organization_id: str, code: str, label: str):
    parent = _record_by_code(db, model, organization_id, code)
    if not parent:
        raise ValueError(f"{label} code {code} was not found; import academic structure in dependency order")
    if not parent.is_active:
        raise ValueError(f"{label} code {code} is archived")
    return parent


def _manual_update_target(db: Session, run: CollegeImportRun, row: dict, model):
    if run.source_type not in {"csv", "xlsx"} or row.get("_manual_action") != "update":
        return None
    record_id = str(row.get("_record_id") or "").strip()
    record = db.get(model, record_id) if record_id else None
    if not record or record.organization_id != run.organization_id:
        raise ValueError("The update target is no longer available")
    if getattr(record, "version", None) != row.get("_record_version"):
        raise ValueError("The record changed after preview; download a new update template")
    return record


def _commit_structure_row(db: Session, run: CollegeImportRun, row: dict):
    model, local_type = STRUCTURE_MODELS[run.resource_type]
    record, manual_overrides = _linked_record(db, run, row, model, local_type)
    created = record is None
    if not created:
        _reject_stale_structure_update(db, run, row)
    if created:
        collision = _unlinked_structure_collision(db, run, row, model)
        if collision:
            descriptor = row.get("code") or f"{row.get('academic_year')} term {row.get('term_number')}"
            raise ValueError(
                f"{descriptor} matches an existing academic record; review and link it before ERP updates are accepted"
            )
        record = model(organization_id=run.organization_id)
        db.add(record)

    if run.resource_type == "departments":
        values = {
            "name": str(row["name"]).strip(),
            "code": _normalized_code(row["code"]),
            "description": _optional_text(row.get("description")),
        }
    elif run.resource_type == "programs":
        department_id = getattr(record, "department_id", None)
        if created or "department_id" not in manual_overrides:
            department = _active_parent(
                db, CollegeDepartment, run.organization_id, row["department_code"], "Department",
            )
            department_id = department.id
        values = {
            "department_id": department_id,
            "name": str(row["name"]).strip(),
            "code": _normalized_code(row["code"]),
            "degree_type": row["degree_type"],
            "duration_semesters": row["duration_semesters"],
        }
    elif run.resource_type == "terms":
        values = {
            "name": str(row["name"]).strip(),
            "academic_year": str(row["academic_year"]).strip(),
            "term_number": row["term_number"],
            "starts_on": date.fromisoformat(row["starts_on"]),
            "ends_on": date.fromisoformat(row["ends_on"]),
            "status": "active" if row["is_current"] else row["status"],
            "is_current": row["is_current"],
        }
    elif run.resource_type == "cohorts":
        program_id = getattr(record, "program_id", None)
        program = db.get(CollegeProgram, program_id) if program_id else None
        if created or "program_id" not in manual_overrides:
            program = _active_parent(
                db, CollegeProgram, run.organization_id, row["program_code"], "Program",
            )
            program_id = program.id
        if not program or program.organization_id != run.organization_id:
            raise ValueError("The manually selected program is no longer available")
        if row["current_semester"] > program.duration_semesters:
            raise ValueError("current_semester exceeds the program duration")
        values = {
            "program_id": program_id,
            "name": str(row["name"]).strip(),
            "code": _normalized_code(row["code"]),
            "admission_year": row["admission_year"],
            "graduation_year": row["graduation_year"],
            "current_semester": row["current_semester"],
            "section": _normalized_section(row.get("section")),
        }
    else:
        department_id = getattr(record, "department_id", None)
        if created or "department_id" not in manual_overrides:
            department = _active_parent(
                db, CollegeDepartment, run.organization_id, row["department_code"], "Department",
            )
            department_id = department.id
        values = {
            "department_id": department_id,
            "name": str(row["name"]).strip(),
            "code": _normalized_code(row["code"]),
            "credits": row["credits"],
            "course_type": row["course_type"],
        }

    changed = _apply_import_values(record, values, manual_overrides)
    if not created and changed:
        record.version += 1
    if run.resource_type == "terms" and row["is_current"] and "is_current" not in manual_overrides:
        other_terms = db.execute(select(CollegeTerm).where(
            CollegeTerm.organization_id == run.organization_id,
            CollegeTerm.id != record.id,
            CollegeTerm.is_current.is_(True),
        )).scalars()
        for term in other_terms:
            term.is_current = False
            if term.status == "active":
                term.status = "closed" if term.ends_on < date.today() else "planned"
            term.version += 1
    db.flush()
    _external_link(db, run, row, local_type, record.id)
    return record


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
            if run.resource_type in STRUCTURE_RESOURCES:
                _commit_structure_row(db, run, row)
                savepoint.commit()
                committed += 1
                continue
            student = _student(db, run.organization_id, str(row["admission_number"]).strip())
            if allowed_student_ids is not None and student and student.id not in allowed_student_ids:
                raise ValueError("Student is outside your College access")
            if run.resource_type == "students":
                manual_student = _manual_update_target(db, run, row, CollegeStudentProfile)
                linked_student, manual_overrides = _linked_record(db, run, row, CollegeStudentProfile, "college_student_profile")
                if manual_student or linked_student:
                    student = manual_student or linked_student
                    if allowed_student_ids is not None and student.id not in allowed_student_ids:
                        raise ValueError("Student is outside your College access")
                elif run.source_type in {"csv", "xlsx"} and student:
                    raise ValueError("A matching student already exists; use a prefilled update template")
                program = db.execute(select(CollegeProgram).where(
                    CollegeProgram.organization_id == run.organization_id,
                    CollegeProgram.code == _normalized_code(row["program_code"]),
                )).scalar_one_or_none()
                cohort = db.execute(select(CollegeCohort).where(
                    CollegeCohort.organization_id == run.organization_id,
                    CollegeCohort.code == _normalized_code(row["cohort_code"]),
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
                student_changed = _apply_import_values(student, {
                    "admission_number": str(row["admission_number"]).strip(),
                    "program_id": program.id,
                    "cohort_id": cohort.id,
                    "current_semester": row.get("current_semester") or 1,
                }, manual_overrides)
                client_changed = _apply_import_values(client, {
                    "first_name": str(row["first_name"]).strip(),
                    "last_name": str(row.get("last_name") or "").strip(),
                    "email": str(row.get("email") or "").strip() or None,
                    "phone": str(row.get("phone") or "").strip() or None,
                }, manual_overrides)
                if (student_changed or client_changed) and (manual_student or linked_student):
                    student.version += 1
                _external_link(db, run, row, "college_student_profile", student.id)
            else:
                if not student:
                    raise ValueError("Student admission number was not found")
                source_key = f"connector:{run.connector_id}" if run.connector_id else run.source_type
                if run.resource_type == "term_results":
                    manual_record = _manual_update_target(db, run, row, CollegeTermResult)
                    record, manual_overrides = _linked_record(
                        db, run, row, CollegeTermResult, "college_term_result",
                    )
                    record = manual_record or record
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
                    elif run.source_type in {"csv", "xlsx"} and row.get("_manual_action") != "update":
                        raise ValueError("A matching term result already exists; use a prefilled update template")
                    changed = _apply_import_values(record, {
                        "sgpa": row.get("sgpa"),
                        "cgpa": row.get("cgpa"),
                        "active_backlogs": row.get("active_backlogs"),
                        "total_backlogs": row.get("total_backlogs"),
                        "credits_earned": row.get("credits_earned"),
                        "published_on": date.fromisoformat(row["published_on"]) if row.get("published_on") else None,
                    }, manual_overrides)
                    if changed and manual_record:
                        record.version += 1
                    record.external_id = str(row.get("external_id")) if row.get("external_id") is not None else None
                    db.flush()
                    _external_link(db, run, row, "college_term_result", record.id)
                elif run.resource_type == "attendance":
                    as_of = date.fromisoformat(row["as_of"])
                    scope = str(row.get("scope") or "overall")
                    manual_record = _manual_update_target(db, run, row, CollegeAttendanceSnapshot)
                    record, manual_overrides = _linked_record(
                        db, run, row, CollegeAttendanceSnapshot, "college_attendance_snapshot",
                    )
                    record = manual_record or record
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
                    elif run.source_type in {"csv", "xlsx"} and row.get("_manual_action") != "update":
                        raise ValueError("A matching attendance snapshot already exists; use a prefilled update template")
                    changed = _apply_import_values(record, {
                        "classes_held": row.get("classes_held") or 0,
                        "classes_attended": row.get("classes_attended") or 0,
                        "attendance_percent": row.get("attendance_percent"),
                        "as_of": as_of,
                        "scope_key": scope,
                    }, manual_overrides)
                    if changed and manual_record:
                        record.version += 1
                    record.external_id = str(row.get("external_id")) if row.get("external_id") is not None else None
                    db.flush()
                    _external_link(db, run, row, "college_attendance_snapshot", record.id)
                elif run.resource_type == "skills":
                    manual_record = _manual_update_target(db, run, row, CollegeCareerEvidence)
                    record, manual_overrides = _linked_record(
                        db, run, row, CollegeCareerEvidence, "college_career_evidence",
                    )
                    record = manual_record or record
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
                    elif run.source_type in {"csv", "xlsx"} and row.get("_manual_action") != "update":
                        raise ValueError("A matching skill already exists; use a prefilled update template")
                    changed = _apply_import_values(record, {
                        "title": str(row["title"]).strip(),
                        "proficiency": str(row.get("proficiency") or "").strip() or None,
                        "evidence_url": str(row.get("evidence_url") or "").strip() or None,
                        "is_verified": bool(row.get("verified")),
                    }, manual_overrides)
                    if changed and manual_record:
                        record.version += 1
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
