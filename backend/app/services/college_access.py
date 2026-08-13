"""College resource scope backed by the enterprise access policy."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    AccessScope, CollegeCohort, CollegeCourseOffering, CollegeDepartment,
    CollegeProgram, CollegeStudentProfile, Employee, User,
)
from app.services.access_policy import policy_v2_enabled, resolve_policy_context
from app.services.rbac import get_user_roles


LEGACY_UNRESTRICTED_ROLES = {"owner", "principal", "placement-head", "academic-admin"}
LEGACY_SCOPED_ROLES = {"hod", "placement-coordinator", "faculty", "class-advisor"}


@dataclass(frozen=True)
class CollegeAccess:
    unrestricted: bool
    student_ids: frozenset[str] = frozenset()
    full_student_ids: frozenset[str] = frozenset()
    department_ids: frozenset[str] = frozenset()
    program_ids: frozenset[str] = frozenset()
    cohort_ids: frozenset[str] = frozenset()
    course_offering_ids: frozenset[str] = frozenset()
    location_ids: frozenset[str] = frozenset()
    policy_version: int = 0
    domain: str = "students"

    def allows_student(self, student_id: str) -> bool:
        return self.unrestricted or student_id in self.student_ids

    def require_student(self, student_id: str) -> None:
        if not self.allows_student(student_id):
            # Do not reveal whether a student exists outside the caller's scope.
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")

    def _require(self, allowed: frozenset[str], value: str, label: str) -> None:
        if not self.unrestricted and value not in allowed:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")

    def require_department(self, department_id: str) -> None:
        self._require(self.department_ids, department_id, "Department")

    def require_program(self, program_id: str) -> None:
        self._require(self.program_ids, program_id, "Program")

    def require_cohort(self, cohort_id: str) -> None:
        self._require(self.cohort_ids, cohort_id, "Cohort")

    def require_course_offering(self, offering_id: str) -> None:
        self._require(self.course_offering_ids, offering_id, "Course offering")

    def allows_course_offering(self, offering_id: str) -> bool:
        return self.unrestricted or offering_id in self.course_offering_ids

    def allows_opportunity(self, rules: dict | None) -> bool:
        if self.unrestricted:
            return True
        return opportunity_rules_match_scope(
            rules,
            department_ids=self.department_ids,
            program_ids=self.program_ids,
            cohort_ids=self.cohort_ids,
        )

    @property
    def constrained_student_ids(self) -> set[str] | None:
        return None if self.unrestricted else set(self.student_ids)


def opportunity_rules_match_scope(
    rules: dict | None,
    *,
    department_ids,
    program_ids,
    cohort_ids,
) -> bool:
    """Return whether placement rules overlap a staff member's assigned scope."""
    available = set(department_ids) | set(program_ids) | set(cohort_ids)
    if not available:
        return False
    rules = rules or {}
    dimensions = (
        (set(rules.get("department_ids") or []), set(department_ids)),
        (set(rules.get("program_ids") or []), set(program_ids)),
        (set(rules.get("cohort_ids") or rules.get("batch_ids") or []), set(cohort_ids)),
    )
    return all(not required or bool(required & allowed) for required, allowed in dimensions)


def resolve_college_access(db: Session, user: User, domain: str = "students") -> CollegeAccess:
    """Resolve College scope. Missing or unreviewed policies never mean full access."""
    if user.organization_id and policy_v2_enabled(db, user.organization_id):
        context = resolve_policy_context(db, user)
        if not context.active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your College data access is awaiting review")
        if context.level(domain) == "none":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This College work area is not included in your access")
        scope = context.scope(domain)
        return CollegeAccess(
            unrestricted=scope.unrestricted,
            student_ids=scope.student_ids,
            full_student_ids=scope.full_student_ids,
            department_ids=scope.department_ids,
            program_ids=scope.program_ids,
            cohort_ids=scope.cohort_ids,
            course_offering_ids=scope.course_offering_ids,
            location_ids=scope.location_ids,
            policy_version=context.policy_version,
            domain=domain,
        )

    # Compatibility path for tenants not yet enabled. It is intentionally
    # fail-closed for unknown and custom roles.
    roles = {role.slug for role in get_user_roles(db, user)}
    if roles & LEGACY_UNRESTRICTED_ROLES:
        return CollegeAccess(unrestricted=True)
    if not roles & LEGACY_SCOPED_ROLES:
        return CollegeAccess(unrestricted=False, domain=domain)

    employee = db.execute(select(Employee).where(
        Employee.organization_id == user.organization_id,
        Employee.user_id == user.id,
        Employee.status == "active",
    )).scalar_one_or_none()
    department_ids: set[str] = set()
    program_ids: set[str] = set()
    cohort_ids: set[str] = set()

    if employee and "hod" in roles:
        department_ids.update(db.execute(select(CollegeDepartment.id).where(
            CollegeDepartment.organization_id == user.organization_id,
            CollegeDepartment.hod_employee_id == employee.id,
        )).scalars())
    if employee and ({"placement-coordinator", "class-advisor"} & roles):
        cohort_ids.update(db.execute(select(CollegeCohort.id).where(
            CollegeCohort.organization_id == user.organization_id,
            CollegeCohort.advisor_employee_id == employee.id,
        )).scalars())
    offering_ids: set[str] = set()
    if employee and "faculty" in roles:
        offering_ids.update(db.execute(select(CollegeCourseOffering.id).where(
            CollegeCourseOffering.organization_id == user.organization_id,
            CollegeCourseOffering.faculty_employee_id == employee.id,
        )).scalars())
        if domain in {"attendance", "assessments"} and offering_ids:
            cohort_ids.update(db.execute(select(CollegeCourseOffering.cohort_id).where(
                CollegeCourseOffering.organization_id == user.organization_id,
                CollegeCourseOffering.id.in_(offering_ids),
            )).scalars())

    scopes = list(db.execute(select(AccessScope).where(
        AccessScope.organization_id == user.organization_id,
        AccessScope.user_id == user.id,
    )).scalars())
    for row in scopes:
        kind = row.scope_type.lower().replace("college.", "")
        if kind == "department":
            department_ids.add(row.scope_value)
        elif kind == "program":
            program_ids.add(row.scope_value)
        elif kind == "cohort":
            cohort_ids.add(row.scope_value)
        elif kind == "course_offering":
            offering_ids.add(row.scope_value)
        elif kind == "assigned" and (row.meta or {}).get("domain") == "college":
            target = (row.meta or {}).get("resource")
            if target == "department":
                department_ids.add(row.scope_value)
            elif target == "program":
                program_ids.add(row.scope_value)
            elif target == "cohort":
                cohort_ids.add(row.scope_value)
            elif target == "course_offering":
                offering_ids.add(row.scope_value)

    student_query = (
        select(
            CollegeStudentProfile.id,
            CollegeProgram.department_id,
            CollegeStudentProfile.program_id,
            CollegeStudentProfile.cohort_id,
        )
        .join(CollegeProgram, CollegeProgram.id == CollegeStudentProfile.program_id)
        .where(CollegeStudentProfile.organization_id == user.organization_id)
    )
    conditions = []
    if department_ids:
        conditions.append(CollegeProgram.department_id.in_(department_ids))
    if program_ids:
        conditions.append(CollegeStudentProfile.program_id.in_(program_ids))
    if cohort_ids:
        conditions.append(CollegeStudentProfile.cohort_id.in_(cohort_ids))
    rows = db.execute(student_query.where(or_(*conditions))).all() if conditions else []
    student_ids = {row.id for row in rows}
    department_ids.update(row.department_id for row in rows)
    program_ids.update(row.program_id for row in rows)
    cohort_ids.update(row.cohort_id for row in rows)
    return CollegeAccess(
        unrestricted=False,
        student_ids=frozenset(student_ids),
        full_student_ids=frozenset(student_ids),
        department_ids=frozenset(department_ids),
        program_ids=frozenset(program_ids),
        cohort_ids=frozenset(cohort_ids),
        course_offering_ids=frozenset(offering_ids),
        domain=domain,
    )


def validate_college_filters(
    access: CollegeAccess,
    *,
    department_id: str | None = None,
    program_id: str | None = None,
    cohort_id: str | None = None,
    cohort_ids: list[str] | set[str] | tuple[str, ...] | None = None,
) -> None:
    if access.unrestricted:
        return
    if department_id and department_id not in access.department_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Department is outside your College access")
    if program_id and program_id not in access.program_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Program is outside your College access")
    if cohort_id and cohort_id not in access.cohort_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cohort is outside your College access")
    if cohort_ids and not set(cohort_ids).issubset(access.cohort_ids):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "One or more cohorts are outside your College access")
