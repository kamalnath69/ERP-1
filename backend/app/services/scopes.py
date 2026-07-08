"""Access-scope service — the enforcement layer for AI tool calls.

The `AccessScope` table stores rows of the form (user_id, scope_type, scope_value).
`scope_type` is FREE-FORM STRING — the tenant defines its own dimensions.
The following types are recognised by the AI filter engine and applied as SQL filters:

    department, academic_unit, level, section, subject, campus, batch,
    faculty_assignment (composite: scope_value = "<subject_id>:<section_id>")

Any other type is stored/displayed but does NOT restrict data automatically —
tenants can still use it for informational tagging or future custom tools.

Rules
-----
* A user with **no** scopes is unrestricted **within their tenant**.
* Scopes of the SAME type are OR'd, scopes of DIFFERENT types are AND'd.
* faculty_assignment scope narrows both `subject_id` AND `section_id` at the
  same time (its scope_value is "subject_id:section_id").
* Super admin bypasses all filtering.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AccessScope,
    AcademicUnit,
    AcademicLevel,
    Department,
    FacultyAssignment,
    Section,
    Student,
    Subject,
    User,
)


KNOWN_TYPES = {
    "department",
    "academic_unit",
    "level",
    "section",
    "subject",
    "campus",
    "batch",
    "faculty_assignment",
}


@dataclass
class ScopeMap:
    by_type: dict[str, list[str]]        # scope_type -> [scope_value, ...]
    meta_by_type: dict[str, list[dict]]  # scope_type -> [meta_dict, ...]

    def is_empty(self) -> bool:
        return not any(self.by_type.values())

    def types(self) -> set[str]:
        return {t for t, v in self.by_type.items() if v}

    def get(self, t: str) -> list[str]:
        return self.by_type.get(t, [])


# ------------------------------------------------------------------ load ---- #

def get_implicit_scopes(db: Session, user: User) -> list[dict]:
    """Compute implicit scopes from faculty_assignments and section advisorship.

    Returns a list of dicts:
        {"scope_type": ..., "scope_value": ..., "source": "faculty_assignment"|"section_advisor",
         "meta": {...}}
    """
    if user.is_super_admin or not user.organization_id:
        return []
    implicit: list[dict] = []

    # Faculty assignments -> subject + section + composite
    fa_rows = db.execute(
        select(FacultyAssignment).where(
            FacultyAssignment.organization_id == user.organization_id,
            FacultyAssignment.faculty_user_id == user.id,
        )
    ).scalars().all()
    for fa in fa_rows:
        implicit.append({
            "scope_type": "subject",
            "scope_value": fa.subject_id,
            "source": "faculty_assignment",
            "meta": {"assignment_id": fa.id, "role": fa.role},
        })
        implicit.append({
            "scope_type": "section",
            "scope_value": fa.section_id,
            "source": "faculty_assignment",
            "meta": {"assignment_id": fa.id, "role": fa.role},
        })
        implicit.append({
            "scope_type": "faculty_assignment",
            "scope_value": f"{fa.subject_id}:{fa.section_id}",
            "source": "faculty_assignment",
            "meta": {"assignment_id": fa.id, "role": fa.role},
        })

    # Section advisor -> section scope for that section
    advisor_rows = db.execute(
        select(Section).where(
            Section.organization_id == user.organization_id,
            Section.advisor_user_id == user.id,
        )
    ).scalars().all()
    for sec in advisor_rows:
        implicit.append({
            "scope_type": "section",
            "scope_value": sec.id,
            "source": "section_advisor",
            "meta": {"section_name": sec.name},
        })

    return implicit


def get_user_scope_map(db: Session, user: User) -> ScopeMap:
    """Effective scope map = explicit access_scopes UNION implicit faculty scopes.

    Deduplicates identical (type, value) pairs across sources.
    """
    if user.is_super_admin:
        return ScopeMap(by_type={}, meta_by_type={})

    by_type: dict[str, list[str]] = {}
    meta_by_type: dict[str, list[dict]] = {}
    seen: set[tuple[str, str]] = set()

    def _add(t: str, v: str, meta: dict | None):
        key = (t, v)
        if key in seen:
            return
        seen.add(key)
        by_type.setdefault(t, []).append(v)
        meta_by_type.setdefault(t, []).append(meta or {})

    # 1) explicit
    rows = db.execute(
        select(AccessScope).where(AccessScope.user_id == user.id)
    ).scalars().all()
    for r in rows:
        _add(r.scope_type, r.scope_value, r.meta)

    # 2) implicit (faculty assignments + section advisorship)
    for imp in get_implicit_scopes(db, user):
        meta = dict(imp.get("meta") or {})
        meta["source"] = imp["source"]
        meta["implicit"] = True
        _add(imp["scope_type"], imp["scope_value"], meta)

    return ScopeMap(by_type=by_type, meta_by_type=meta_by_type)


# --------------------------------------------------------- describe (human) - #

def describe_scopes(db: Session, user: User, scopes: ScopeMap | None = None) -> str:
    """Return a human-readable summary of the user's scopes for AI refusal messages."""
    scopes = scopes or get_user_scope_map(db, user)
    if scopes.is_empty():
        return "You have access to the entire organization."

    parts: list[str] = []
    for t, values in scopes.by_type.items():
        labels = _resolve_labels(db, user, t, values)
        if labels:
            parts.append(f"{t}: {', '.join(labels)}")
        else:
            parts.append(f"{t}: {', '.join(values)}")
    return "Your AI access is limited to — " + " · ".join(parts)


def _resolve_labels(db: Session, user: User, scope_type: str, values: list[str]) -> list[str]:
    """Best-effort ID -> human name resolution for known scope types."""
    org = user.organization_id
    if not values:
        return []
    if scope_type == "department":
        rows = db.execute(
            select(Department.name).where(
                Department.organization_id == org, Department.id.in_(values)
            )
        ).scalars().all()
        return list(rows)
    if scope_type == "section":
        rows = db.execute(
            select(Section.name, Section.id).where(
                Section.organization_id == org, Section.id.in_(values)
            )
        ).all()
        return [f"Section {r[0]}" for r in rows]
    if scope_type == "subject":
        rows = db.execute(
            select(Subject.name, Subject.code).where(
                Subject.organization_id == org, Subject.id.in_(values)
            )
        ).all()
        return [f"{r[0]} ({r[1]})" for r in rows]
    if scope_type == "academic_unit":
        rows = db.execute(
            select(AcademicUnit.name).where(
                AcademicUnit.organization_id == org, AcademicUnit.id.in_(values)
            )
        ).scalars().all()
        return list(rows)
    if scope_type == "level":
        rows = db.execute(
            select(AcademicLevel.name).where(
                AcademicLevel.organization_id == org, AcademicLevel.id.in_(values)
            )
        ).scalars().all()
        return list(rows)
    if scope_type == "faculty_assignment":
        labels: list[str] = []
        for v in values:
            try:
                sub_id, sec_id = v.split(":", 1)
            except ValueError:
                labels.append(v)
                continue
            sub = db.get(Subject, sub_id)
            sec = db.get(Section, sec_id)
            sub_label = f"{sub.name} ({sub.code})" if sub else sub_id
            sec_label = f"Section {sec.name}" if sec else sec_id
            labels.append(f"{sub_label} / {sec_label}")
        return labels
    # unknown / custom
    return values


# ---------------------------------------- entity-in-scope predicate helpers - #

class ScopeViolation(Exception):
    """Raised by AI tools when the caller tries to reach outside their scopes."""

    def __init__(self, message: str, meta: dict | None = None):
        super().__init__(message)
        self.message = message
        self.meta = meta or {}


def _fa_matches(db: Session, scopes: ScopeMap, subject_id: str | None, section_id: str | None) -> bool | None:
    """Faculty-assignment scope check. Returns True/False if the scope type is present,
    or None when the scope type is not configured (i.e. skip)."""
    fa_vals = scopes.get("faculty_assignment")
    if not fa_vals:
        return None
    if not subject_id and not section_id:
        return False
    for v in fa_vals:
        try:
            s_id, sec_id = v.split(":", 1)
        except ValueError:
            continue
        if (not subject_id or subject_id == s_id) and (not section_id or section_id == sec_id):
            return True
    return False


def student_in_scope(db: Session, user: User, student: Student, scopes: ScopeMap | None = None) -> bool:
    """Return True if `student` falls within the user's configured scopes."""
    if user.is_super_admin:
        return True
    scopes = scopes or get_user_scope_map(db, user)
    if scopes.is_empty():
        return True

    checks: list[bool] = []

    if "department" in scopes.by_type:
        checks.append(student.department_id in scopes.get("department") if student.department_id else False)
    if "section" in scopes.by_type:
        checks.append(student.section_id in scopes.get("section") if student.section_id else False)

    # Academic unit / level / campus / batch — resolve via student's section (if any).
    if any(t in scopes.by_type for t in ("academic_unit", "level", "campus", "batch")):
        sec = db.get(Section, student.section_id) if student.section_id else None
        level_id = sec.level_id if sec else None
        level = db.get(AcademicLevel, level_id) if level_id else None
        au_id = level.unit_id if level and hasattr(level, "unit_id") else None
        au = db.get(AcademicUnit, au_id) if au_id else None
        if "level" in scopes.by_type:
            checks.append(level_id in scopes.get("level") if level_id else False)
        if "academic_unit" in scopes.by_type:
            checks.append(au_id in scopes.get("academic_unit") if au_id else False)
        # campus / batch left as no-op unless the tenant later attaches these to Student.

    # Subject / faculty_assignment: a student is in-scope for a subject if the subject is offered
    # to the student's section. We conservatively skip subject-only student checks (a subject scope
    # narrows attendance/marks queries, not student membership directly).
    if "subject" in scopes.by_type and "section" not in scopes.by_type:
        # a subject scope, without a section scope, does NOT restrict student list; keep permissive.
        pass

    fa = _fa_matches(db, scopes, subject_id=None, section_id=student.section_id)
    if fa is not None:
        checks.append(fa)

    # AND across scope types
    return all(checks) if checks else True


def entity_in_scope(db: Session, user: User, kind: str, entity_id: str) -> bool:
    """Generic in-scope check for common entities: department|section|subject|student."""
    if user.is_super_admin:
        return True
    scopes = get_user_scope_map(db, user)
    if scopes.is_empty():
        return True

    if kind == "student":
        s = db.get(Student, entity_id)
        return bool(s) and student_in_scope(db, user, s, scopes)
    if kind == "department":
        if "department" in scopes.by_type:
            return entity_id in scopes.get("department")
        return True
    if kind == "section":
        if "section" in scopes.by_type:
            return entity_id in scopes.get("section")
        # section not restricted → check via department scope
        if "department" in scopes.by_type:
            sec = db.get(Section, entity_id)
            if not sec:
                return False
            level = db.get(AcademicLevel, sec.level_id) if sec.level_id else None
            au = db.get(AcademicUnit, level.unit_id) if level and level.unit_id else None
            dept_id = au.department_id if au and au.department_id else None
            return dept_id in scopes.get("department") if dept_id else False
        return True
    if kind == "subject":
        if "subject" in scopes.by_type:
            return entity_id in scopes.get("subject")
        if "department" in scopes.by_type:
            sub = db.get(Subject, entity_id)
            return bool(sub) and sub.department_id in scopes.get("department") if sub and sub.department_id else False
        return True
    return True


# --------------------------------------------------------- SQL filter builders #

def apply_student_scope(stmt, scopes: ScopeMap):
    """Attach scope filters to a `select(Student)` statement.

    Note: `stmt` should already have the tenant filter applied.
    """
    if scopes.is_empty():
        return stmt
    clauses = []
    if "department" in scopes.by_type:
        clauses.append(Student.department_id.in_(scopes.get("department")))
    if "section" in scopes.by_type:
        clauses.append(Student.section_id.in_(scopes.get("section")))
    # Aggregate other section-derived scopes via subquery over Section
    section_filters = _section_ids_from_scope(scopes)
    if section_filters is not None:
        clauses.append(Student.section_id.in_(section_filters))
    if clauses:
        stmt = stmt.where(and_(*clauses))
    return stmt


def _section_ids_from_scope(scopes: ScopeMap):
    """Return a sub-select of section IDs implied by academic_unit/level scopes,
    or None if none of those scopes are configured."""
    needs = [t for t in ("academic_unit", "level") if t in scopes.by_type]
    if not needs:
        return None
    q = select(Section.id)
    if "level" in scopes.by_type:
        q = q.where(Section.level_id.in_(scopes.get("level")))
    if "academic_unit" in scopes.by_type:
        # academic_unit -> academic_level -> section
        level_ids_sub = select(AcademicLevel.id).where(AcademicLevel.unit_id.in_(scopes.get("academic_unit")))
        q = q.where(Section.level_id.in_(level_ids_sub))
    return q


def apply_section_scope(stmt, scopes: ScopeMap):
    """Filter a `select(Section)` (or Attendance/Marks joined-on-section) by scope."""
    if scopes.is_empty():
        return stmt
    clauses = []
    if "section" in scopes.by_type:
        clauses.append(Section.id.in_(scopes.get("section")))
    if "level" in scopes.by_type:
        clauses.append(Section.level_id.in_(scopes.get("level")))
    if "academic_unit" in scopes.by_type:
        level_ids_sub = select(AcademicLevel.id).where(AcademicLevel.unit_id.in_(scopes.get("academic_unit")))
        clauses.append(Section.level_id.in_(level_ids_sub))
    if clauses:
        stmt = stmt.where(and_(*clauses))
    return stmt


def apply_subject_scope(stmt, scopes: ScopeMap):
    if scopes.is_empty():
        return stmt
    clauses = []
    if "subject" in scopes.by_type:
        clauses.append(Subject.id.in_(scopes.get("subject")))
    if "department" in scopes.by_type:
        clauses.append(Subject.department_id.in_(scopes.get("department")))
    if clauses:
        stmt = stmt.where(and_(*clauses))
    return stmt


def apply_department_scope(stmt, scopes: ScopeMap):
    if scopes.is_empty():
        return stmt
    if "department" in scopes.by_type:
        stmt = stmt.where(Department.id.in_(scopes.get("department")))
    return stmt


# ------------------------------------------------------- catalog / suggestions #

def scope_catalog(db: Session, org_id: str) -> dict:
    """Return the list of known + tenant-defined scope types + suggested value pickers."""
    # Every distinct scope_type ever used in the org (drives autocomplete)
    used_rows = db.execute(
        select(AccessScope.scope_type).where(AccessScope.organization_id == org_id).distinct()
    ).scalars().all()
    tenant_types = sorted(set(used_rows))

    departments = db.execute(
        select(Department.id, Department.name).where(Department.organization_id == org_id)
    ).all()
    sections = db.execute(
        select(Section.id, Section.name, Section.level_id).where(Section.organization_id == org_id)
    ).all()
    subjects = db.execute(
        select(Subject.id, Subject.name, Subject.code).where(Subject.organization_id == org_id)
    ).all()
    academic_units = db.execute(
        select(AcademicUnit.id, AcademicUnit.name).where(AcademicUnit.organization_id == org_id)
    ).all()
    levels = db.execute(
        select(AcademicLevel.id, AcademicLevel.name).where(AcademicLevel.organization_id == org_id)
    ).all()

    return {
        "known_types": sorted(KNOWN_TYPES),
        "tenant_types": tenant_types,
        "pickers": {
            "department": [{"value": r[0], "label": r[1]} for r in departments],
            "section": [{"value": r[0], "label": f"Section {r[1]}"} for r in sections],
            "subject": [{"value": r[0], "label": f"{r[1]} ({r[2]})"} for r in subjects],
            "academic_unit": [{"value": r[0], "label": r[1]} for r in academic_units],
            "level": [{"value": r[0], "label": r[1]} for r in levels],
        },
    }
