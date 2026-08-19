"""College semantic execution with scope-first SQLAlchemy queries."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, case, exists, func, literal, or_, select
from sqlalchemy.orm import Session

from app.ai.access import AccessEnvelope, AccessViolation
from app.ai.catalog import SemanticCatalog
from app.ai.contracts import (
    Artifact, AssistantOutcome, AssistantResponse, EntityRef, FilterOperator,
    QueryFilter, QueryGoal, SemanticQuery, Suggestion,
)
from app.ai.domains.common import identifier, json_value, observation, security
from app.models import (
    Client, CollegeAssessment, CollegeAssessmentComponent, CollegeAssessmentScore, CollegeAttendanceSnapshot,
    CollegeCareerEvidence, CollegeCareerProfile, CollegeCohort, CollegeCodingSnapshot,
    CollegeCourse, CollegeCourseOffering, CollegeDepartment, CollegePlacementApplication,
    CollegePlacementCompany, CollegePlacementOffer, CollegePlacementOpportunity,
    CollegePreparationActivity, CollegeProgram, CollegeReadinessPolicy,
    CollegeReadinessSnapshot, CollegeStudentProfile, CollegeTerm, CollegeTermResult, User,
)
from app.services.entity_resolution import resolve_entities, validate_entity_ref
from app.services.college_placement import fee_clearance_by_student, opportunity_eligibility_rules


ACADEMIC_FIELDS = {
    "cgpa", "sgpa", "active_backlogs", "academic_history",
    "subject", "subject_score", "improvement",
}
ATTENDANCE_FIELDS = {"attendance_percent", "attendance_history"}
READINESS_FIELDS = {
    "readiness_score", "readiness_band", "readiness_coverage", "skills", "projects",
    "certifications", "skill_count", "project_count", "certification_count",
    "internship_count", "training_count", "profile_complete",
}
CODING_FIELDS = {"coding_total", "coding_languages"}
PLACEMENT_FIELDS = {
    "placement_status", "eligible_company_count", "match_percent",
    "eligibility_coverage", "offer_count", "highest_package", "offers",
}
ELIGIBILITY_RULE_KEYS = {
    "minimum_cgpa", "maximum_active_backlogs", "minimum_attendance",
    "minimum_solved", "required_skills", "require_fee_clearance",
    "program_ids", "department_ids", "cohort_ids", "batch_ids",
    "graduation_years",
}


@dataclass(frozen=True)
class StudentResolution:
    ids: list[str]
    labels: dict[str, str]
    clarification: AssistantResponse | None = None


def _definitions_for_fields(fields: set[str], definitions: dict) -> dict[str, str]:
    result = {}
    if "attendance_percent" in fields:
        result["low attendance"] = f"below {definitions['low_attendance_percent']:g}%"
    if "cgpa" in fields:
        result["high CGPA"] = f"at least {definitions['high_cgpa']:g}"
    if fields & {"readiness_score", "readiness_band", "readiness_coverage"}:
        result["overall good student"] = "active placement-readiness policy with minimum evidence coverage"
    return result


def _required_domains(catalog: SemanticCatalog, query: SemanticQuery, fields: list[str]) -> set[str]:
    domains = set()
    for key in fields:
        domains.update(catalog.field(query.entity, key).domains)
    for item in (*query.filters, *query.sort):
        domains.update(catalog.field(query.entity, item.field).domains)
    for key in query.group_by:
        domains.update(catalog.field(query.entity, key).domains)
    for key in query.metrics:
        domains.update(catalog.metric(key).domains)
    domains.discard("students")
    return domains


def _clarification_response(query: SemanticQuery, options: list[dict], envelope: AccessEnvelope) -> AssistantResponse:
    clarification_id = identifier("clarify")
    artifact = Artifact(
        id=identifier("artifact"), type="clarification", title="Which record did you mean?",
        data={
            "clarification_id": clarification_id,
            "entity_kind": query.entity,
            "options": [{
                "entity": {"kind": item["kind"], "id": item["id"], "label": item["display_name"]},
                "label": item["display_name"], "meta": item.get("display_meta"),
            } for item in options],
        },
        security=security(
            permissions=("college.students.view",), domains=("students",),
            entity_ids=(item["id"] for item in options),
        ),
    )
    return AssistantResponse(
        outcome=AssistantOutcome.CLARIFICATION,
        answer="I found more than one authorized student with that name. Choose one and I'll continue your original question.",
        artifacts=[artifact], scope=envelope.public_scope(),
    )


def _subject_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
    definitions: dict,
    scope_ids: set[str] | None,
) -> AssistantResponse:
    score_percent = case(
        (
            and_(CollegeAssessmentScore.marks_awarded.is_not(None), CollegeAssessment.max_marks > 0),
            CollegeAssessmentScore.marks_awarded * 100 / CollegeAssessment.max_marks,
        ),
        else_=CollegeAssessmentScore.calculated_score,
    )
    configured_pass = case(
        (
            and_(CollegeAssessmentComponent.pass_marks.is_not(None), CollegeAssessment.max_marks > 0),
            CollegeAssessmentComponent.pass_marks * 100 / CollegeAssessment.max_marks,
        ),
        else_=Decimal(str(definitions["subject_weak_percent"])),
    )
    statement = (
        select(
            CollegeCourse.id.label("id"), CollegeCourse.name.label("name"),
            CollegeCourse.code.label("code"), CollegeDepartment.name.label("department"),
            func.avg(score_percent).label("average_score"),
            func.count(CollegeAssessmentScore.id).label("student_count"),
            func.sum(case((score_percent < configured_pass, 1), else_=0)).label("failure_count"),
            func.max(CollegeAssessmentScore.updated_at).label("source_updated_at"),
        )
        .select_from(CollegeAssessmentScore)
        .join(CollegeAssessment, CollegeAssessment.id == CollegeAssessmentScore.assessment_id)
        .join(CollegeCourseOffering, CollegeCourseOffering.id == CollegeAssessment.offering_id)
        .join(CollegeCourse, CollegeCourse.id == CollegeCourseOffering.course_id)
        .join(CollegeDepartment, CollegeDepartment.id == CollegeCourse.department_id)
        .outerjoin(CollegeAssessmentComponent, CollegeAssessmentComponent.id == CollegeAssessment.scheme_component_id)
        .where(
            CollegeAssessmentScore.organization_id == envelope.organization_id,
            CollegeAssessment.status == "published",
            score_percent.is_not(None),
        )
        .group_by(CollegeCourse.id, CollegeCourse.name, CollegeCourse.code, CollegeDepartment.name)
    )
    if scope_ids is not None:
        statement = statement.where(CollegeAssessmentScore.student_profile_id.in_(scope_ids))
    for item in query.filters:
        if item.field == "name":
            statement = _apply_filter(statement, CollegeCourse.name, item.operator, item.value)
        elif item.field == "department":
            statement = statement.where(or_(
                func.lower(CollegeDepartment.name).contains(str(item.value).casefold()),
                func.lower(CollegeDepartment.code).contains(str(item.value).casefold()),
            ))
    rows = []
    for row in db.execute(statement.limit(500)).all():
        item = dict(row._mapping)
        count = int(item["student_count"] or 0)
        item["average_score"] = round(float(item["average_score"]), 2) if item["average_score"] is not None else None
        item["failure_rate"] = round(int(item.pop("failure_count") or 0) * 100 / count, 2) if count else None
        rows.append({key: json_value(value) for key, value in item.items()})
    sort_field = query.sort[0].field if query.sort else (
        "failure_rate" if query.metrics == ["failure_rate"] or "failure" in (query.requested_analysis or "") else "average_score"
    )
    reverse = not query.sort or query.sort[0].direction == "desc"
    rows.sort(key=lambda item: (item.get(sort_field) is not None, item.get(sort_field) or -math.inf), reverse=reverse)
    rows = rows[:query.limit]
    if not rows:
        return AssistantResponse(
            outcome=AssistantOutcome.EMPTY,
            answer="I found no published subject results in your authorized assessment scope.",
            scope=envelope.public_scope(),
        )
    obs = observation(
        kind="subject_performance", entity="subject", facts={"items": rows},
        source="Edvatiq published assessment scores",
        source_timestamp=max((item.get("source_updated_at") for item in rows if item.get("source_updated_at")), default=None),
        sample_size=sum(item["student_count"] for item in rows), population_size=len(rows),
        definitions={"weak or failed": f"configured pass mark when available, otherwise below {definitions['subject_weak_percent']:g}%"},
        authorized_scope=envelope.scope_label(),
    )
    leader = rows[0]
    descriptor = "highest failure rate" if sort_field == "failure_rate" else "highest average score"
    answer = f"{leader['name']} has the {descriptor} in your authorized published results."
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS, answer=answer,
        artifacts=[Artifact(
            id=identifier("artifact"), type="ranking", title="Subject performance",
            data={"items": rows, "sort_field": sort_field}, evidence_ids=[obs.id],
            security=security(
                permissions=("college.assessments.view",), domains=("assessments",),
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _subject_attendance_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
    scope_ids: set[str] | None,
) -> AssistantResponse:
    latest_statement = select(
        CollegeAttendanceSnapshot.student_profile_id.label("student_id"),
        CollegeAttendanceSnapshot.course_id.label("course_id"),
        CollegeAttendanceSnapshot.attendance_percent.label("attendance_percent"),
        CollegeAttendanceSnapshot.updated_at.label("source_updated_at"),
        func.row_number().over(
            partition_by=(
                CollegeAttendanceSnapshot.student_profile_id,
                CollegeAttendanceSnapshot.course_id,
            ),
            order_by=(
                CollegeAttendanceSnapshot.as_of.desc(),
                CollegeAttendanceSnapshot.created_at.desc(),
            ),
        ).label("position"),
    ).where(
        CollegeAttendanceSnapshot.organization_id == envelope.organization_id,
        CollegeAttendanceSnapshot.course_id.is_not(None),
        CollegeAttendanceSnapshot.attendance_percent.is_not(None),
    )
    if scope_ids is not None:
        latest_statement = latest_statement.where(
            CollegeAttendanceSnapshot.student_profile_id.in_(scope_ids),
        )
    latest = latest_statement.subquery()
    statement = select(
        CollegeCourse.id.label("id"), CollegeCourse.name.label("name"),
        CollegeCourse.code.label("code"), CollegeDepartment.name.label("department"),
        func.avg(latest.c.attendance_percent).label("attendance_percent"),
        func.count(func.distinct(latest.c.student_id)).label("student_count"),
        func.max(latest.c.source_updated_at).label("source_updated_at"),
    ).select_from(latest).join(
        CollegeCourse, CollegeCourse.id == latest.c.course_id,
    ).join(
        CollegeDepartment, CollegeDepartment.id == CollegeCourse.department_id,
    ).where(latest.c.position == 1).group_by(
        CollegeCourse.id, CollegeCourse.name, CollegeCourse.code,
        CollegeDepartment.name,
    )
    for item in query.filters:
        if item.field == "name":
            statement = _apply_filter(statement, CollegeCourse.name, item.operator, item.value)
        elif item.field == "department":
            statement = statement.where(or_(
                func.lower(CollegeDepartment.name).contains(str(item.value).casefold()),
                func.lower(CollegeDepartment.code).contains(str(item.value).casefold()),
            ))
    rows = []
    for row in db.execute(statement.limit(500)).all():
        item = dict(row._mapping)
        item["attendance_percent"] = round(float(item["attendance_percent"]), 2)
        item["student_count"] = int(item["student_count"] or 0)
        rows.append({key: json_value(value) for key, value in item.items()})
    direction = query.sort[0].direction if query.sort else "desc"
    rows.sort(
        key=lambda item: item.get("attendance_percent", -math.inf),
        reverse=direction == "desc",
    )
    rows = rows[:query.limit]
    if not rows:
        return AssistantResponse(
            outcome=AssistantOutcome.EMPTY,
            answer="I found no subject-level attendance evidence in your authorized scope.",
            scope=envelope.public_scope(),
        )
    obs = observation(
        kind="subject_attendance", entity="subject", facts={"items": rows},
        source="Edvatiq latest subject attendance snapshots",
        source_timestamp=max(
            (item.get("source_updated_at") for item in rows if item.get("source_updated_at")),
            default=None,
        ),
        sample_size=sum(item["student_count"] for item in rows),
        population_size=len(rows),
        definitions={"subject attendance": "mean of each authorized student's latest snapshot for that subject"},
        authorized_scope=envelope.scope_label(),
    )
    leader = rows[0]
    descriptor = "lowest" if direction == "asc" else "highest"
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS,
        answer=(
            f"{leader['name']} has the {descriptor} recorded subject attendance at "
            f"{leader['attendance_percent']:.2f}% in your authorized scope."
        ),
        artifacts=[Artifact(
            id=identifier("artifact"), type="ranking", title="Subject attendance",
            data={"items": rows, "sort_field": "attendance_percent"},
            evidence_ids=[obs.id],
            security=security(
                permissions=("college.attendance.view",),
                domains=("students", "attendance"),
                entity_ids=(item["id"] for item in rows),
                scope={"population": sum(item["student_count"] for item in rows)},
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _subject_students_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
    definitions: dict,
    scope_ids: set[str] | None,
) -> AssistantResponse:
    if query.group_by:
        return _subject_group_response(db, query, envelope, scope_ids)
    score_percent = case(
        (
            and_(CollegeAssessmentScore.marks_awarded.is_not(None), CollegeAssessment.max_marks > 0),
            CollegeAssessmentScore.marks_awarded * 100 / CollegeAssessment.max_marks,
        ),
        else_=CollegeAssessmentScore.calculated_score,
    )
    statement = (
        select(
            CollegeStudentProfile.id.label("id"),
            func.trim(Client.first_name + literal(" ") + Client.last_name).label("name"),
            CollegeCourse.name.label("subject"),
            func.avg(score_percent).label("subject_score"),
        )
        .select_from(CollegeAssessmentScore)
        .join(CollegeStudentProfile, CollegeStudentProfile.id == CollegeAssessmentScore.student_profile_id)
        .join(Client, Client.id == CollegeStudentProfile.client_id)
        .join(CollegeAssessment, CollegeAssessment.id == CollegeAssessmentScore.assessment_id)
        .join(CollegeCourseOffering, CollegeCourseOffering.id == CollegeAssessment.offering_id)
        .join(CollegeCourse, CollegeCourse.id == CollegeCourseOffering.course_id)
        .where(
            CollegeAssessmentScore.organization_id == envelope.organization_id,
            CollegeAssessment.status == "published", score_percent.is_not(None),
        )
        .group_by(CollegeStudentProfile.id, Client.first_name, Client.last_name, CollegeCourse.name)
    )
    if scope_ids is not None:
        statement = statement.where(CollegeStudentProfile.id.in_(scope_ids))
    for item in query.filters:
        if item.field == "subject":
            statement = statement.where(func.lower(CollegeCourse.name).contains(str(item.value).casefold()))
        elif item.field == "subject_score":
            aggregate = func.avg(score_percent)
            clauses = {
                FilterOperator.EQ: aggregate == item.value,
                FilterOperator.NE: aggregate != item.value,
                FilterOperator.GT: aggregate > item.value,
                FilterOperator.GTE: aggregate >= item.value,
                FilterOperator.LT: aggregate < item.value,
                FilterOperator.LTE: aggregate <= item.value,
            }
            if item.operator in clauses:
                statement = statement.having(clauses[item.operator])
    rows = [{key: json_value(value) for key, value in dict(row._mapping).items()} for row in db.execute(statement.limit(query.limit)).all()]
    if not rows:
        return AssistantResponse(
            outcome=AssistantOutcome.EMPTY,
            answer="I found no students matching that subject-performance rule in your authorized scope.",
            scope=envelope.public_scope(),
        )
    obs = observation(
        kind="student_subject_performance", entity="student", facts={"items": rows},
        source="Edvatiq published assessment scores", sample_size=len(rows),
        definitions={"weak subject": f"below {definitions['subject_weak_percent']:g}% unless the subject has a configured pass mark"},
        authorized_scope=envelope.scope_label(len(rows)),
    )
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS,
        answer=f"I found {len(rows)} matching student-subject records in your authorized scope.",
        artifacts=[Artifact(
            id=identifier("artifact"), type="records", title="Subject support candidates",
            data={"items": rows, "total": len(rows)}, evidence_ids=[obs.id],
            security=security(
                permissions=("college.assessments.view",), domains=("students", "assessments"),
                entity_ids=(item["id"] for item in rows),
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _subject_group_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
    scope_ids: set[str] | None,
) -> AssistantResponse:
    score_percent = case(
        (
            and_(CollegeAssessmentScore.marks_awarded.is_not(None), CollegeAssessment.max_marks > 0),
            CollegeAssessmentScore.marks_awarded * 100 / CollegeAssessment.max_marks,
        ),
        else_=CollegeAssessmentScore.calculated_score,
    )
    group_columns = []
    if "department" in query.group_by:
        group_columns.append(CollegeDepartment.name)
    if "cohort" in query.group_by:
        group_columns.append(CollegeCohort.name)
    if not group_columns:
        group_columns.append(CollegeCohort.name)
    statement = select(
        *[column.label(f"group_{index}") for index, column in enumerate(group_columns)],
        CollegeCourse.name.label("subject"),
        func.avg(score_percent).label("average_score"),
        func.count(func.distinct(CollegeAssessmentScore.student_profile_id)).label("student_count"),
        func.max(CollegeAssessmentScore.updated_at).label("source_updated_at"),
    ).select_from(CollegeAssessmentScore).join(
        CollegeStudentProfile,
        CollegeStudentProfile.id == CollegeAssessmentScore.student_profile_id,
    ).join(
        CollegeProgram, CollegeProgram.id == CollegeStudentProfile.program_id,
    ).join(
        CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id,
    ).join(
        CollegeCohort, CollegeCohort.id == CollegeStudentProfile.cohort_id,
    ).join(
        CollegeAssessment, CollegeAssessment.id == CollegeAssessmentScore.assessment_id,
    ).join(
        CollegeCourseOffering, CollegeCourseOffering.id == CollegeAssessment.offering_id,
    ).join(
        CollegeCourse, CollegeCourse.id == CollegeCourseOffering.course_id,
    ).where(
        CollegeAssessmentScore.organization_id == envelope.organization_id,
        CollegeAssessment.status == "published", score_percent.is_not(None),
    ).group_by(*group_columns, CollegeCourse.name)
    if scope_ids is not None:
        statement = statement.where(CollegeStudentProfile.id.in_(scope_ids))
    for item in query.filters:
        needle = str(item.value).casefold()
        if item.field == "subject":
            statement = statement.where(func.lower(CollegeCourse.name).contains(needle))
        elif item.field == "department":
            values = item.value if isinstance(item.value, list) else [item.value]
            statement = statement.where(or_(*[
                or_(
                    func.lower(CollegeDepartment.name).contains(str(value).casefold()),
                    func.lower(CollegeDepartment.code) == str(value).casefold(),
                ) for value in values
            ]))
        elif item.field == "cohort":
            statement = statement.where(or_(
                func.lower(CollegeCohort.name).contains(needle),
                func.lower(CollegeCohort.code).contains(needle),
            ))
        elif item.field == "section":
            values = item.value if isinstance(item.value, list) else [item.value]
            statement = statement.where(
                func.lower(CollegeCohort.section).in_([str(value).casefold() for value in values]),
            )
    rows = []
    for row in db.execute(statement.limit(500)).all():
        item = dict(row._mapping)
        labels = [item.pop(f"group_{index}") for index in range(len(group_columns))]
        item["group"] = " / ".join(str(value) for value in labels)
        item["average_score"] = round(float(item["average_score"]), 2)
        item["student_count"] = int(item["student_count"] or 0)
        rows.append({key: json_value(value) for key, value in item.items()})
    ascending = bool(query.sort and query.sort[0].direction == "asc")
    rows.sort(
        key=lambda item: (item["average_score"], item["group"].casefold()),
        reverse=not ascending,
    )
    rows = rows[:query.limit]
    if not rows:
        return AssistantResponse(
            outcome=AssistantOutcome.EMPTY,
            answer="I found no matching published subject results in your authorized scope.",
            scope=envelope.public_scope(),
        )
    obs = observation(
        kind="subject_group_comparison", entity="student", facts={"items": rows},
        source="Edvatiq published assessment scores",
        source_timestamp=max(
            (item.get("source_updated_at") for item in rows if item.get("source_updated_at")),
            default=None,
        ),
        sample_size=sum(item["student_count"] for item in rows),
        population_size=sum(item["student_count"] for item in rows),
        definitions={"average score": "mean normalized score from published assessments"},
        authorized_scope=envelope.scope_label(),
    )
    leader = rows[0]
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS,
        answer=(
            f"{leader['group']} has the {'lowest' if ascending else 'highest'} average in {leader['subject']} at "
            f"{leader['average_score']:.2f}% among the authorized comparison groups."
        ),
        artifacts=[Artifact(
            id=identifier("artifact"), type="comparison", title="Subject performance by group",
            data={"items": rows, "sort_field": "average_score"},
            evidence_ids=[obs.id],
            security=security(
                permissions=("college.assessments.view",),
                domains=("students", "assessments"),
                scope={"population": sum(item["student_count"] for item in rows)},
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _subject_trend_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
    scope_ids: set[str] | None,
    *,
    background: bool = False,
) -> AssistantResponse:
    score_percent = case(
        (
            and_(CollegeAssessmentScore.marks_awarded.is_not(None), CollegeAssessment.max_marks > 0),
            CollegeAssessmentScore.marks_awarded * 100 / CollegeAssessment.max_marks,
        ),
        else_=CollegeAssessmentScore.calculated_score,
    )
    statement = (
        select(
            CollegeCourse.id.label("id"), CollegeCourse.name.label("name"),
            CollegeCourse.code.label("code"), CollegeTerm.id.label("term_id"),
            CollegeTerm.name.label("term"), CollegeTerm.starts_on.label("term_starts_on"),
            func.avg(score_percent).label("average_score"),
            func.count(func.distinct(CollegeAssessmentScore.student_profile_id)).label("student_count"),
            func.max(CollegeAssessmentScore.updated_at).label("source_updated_at"),
        )
        .select_from(CollegeAssessmentScore)
        .join(CollegeAssessment, CollegeAssessment.id == CollegeAssessmentScore.assessment_id)
        .join(CollegeCourseOffering, CollegeCourseOffering.id == CollegeAssessment.offering_id)
        .join(CollegeCourse, CollegeCourse.id == CollegeCourseOffering.course_id)
        .join(CollegeTerm, CollegeTerm.id == CollegeCourseOffering.term_id)
        .join(CollegeDepartment, CollegeDepartment.id == CollegeCourse.department_id)
        .where(
            CollegeAssessmentScore.organization_id == envelope.organization_id,
            CollegeAssessment.organization_id == envelope.organization_id,
            CollegeCourseOffering.organization_id == envelope.organization_id,
            CollegeCourse.organization_id == envelope.organization_id,
            CollegeTerm.organization_id == envelope.organization_id,
            CollegeAssessment.status == "published",
            score_percent.is_not(None),
        )
        .group_by(
            CollegeCourse.id, CollegeCourse.name, CollegeCourse.code,
            CollegeTerm.id, CollegeTerm.name, CollegeTerm.starts_on,
        )
    )
    if scope_ids is not None:
        statement = statement.where(CollegeAssessmentScore.student_profile_id.in_(scope_ids))
    for item in query.filters:
        if item.field == "name":
            statement = _apply_filter(statement, CollegeCourse.name, item.operator, item.value)
        elif item.field == "department":
            values = item.value if isinstance(item.value, list) else [item.value]
            statement = statement.where(or_(*[
                or_(
                    func.lower(CollegeDepartment.name).contains(str(value).casefold()),
                    func.lower(CollegeDepartment.code) == str(value).casefold(),
                )
                for value in values
            ]))

    population_statement = statement.with_only_columns(
        func.count(func.distinct(CollegeAssessmentScore.student_profile_id)),
    ).group_by(None).order_by(None)
    population = int(db.scalar(population_statement) or 0)
    row_limit = 50000 if background else 5000
    period_rows = list(db.execute(statement.order_by(
        CollegeCourse.id, CollegeTerm.starts_on.desc(), CollegeTerm.id,
    ).limit(row_limit + 1)).all())
    if len(period_rows) > row_limit:
        return AssistantResponse(
            outcome=AssistantOutcome.UNAVAILABLE if background else AssistantOutcome.PROCESSING,
            answer=(
                "This subject trend exceeds the background safety limit. Narrow the subject or student population."
                if background else
                "This subject trend exceeds the interactive limit and has been queued for background analysis."
            ),
            artifacts=[] if background else [Artifact(
                id=identifier("artifact"), type="processing", title="Subject trend queued",
                data={"authorized_population": population, "period_limit": row_limit},
                security=security(
                    permissions=("college.assessments.view",), domains=("assessments",),
                    scope={"population": population},
                ),
            )], scope=envelope.public_scope(),
        )

    by_subject: dict[str, list[dict]] = defaultdict(list)
    for row in period_rows:
        item = dict(row._mapping)
        if item["average_score"] is None:
            continue
        item["average_score"] = round(float(item["average_score"]), 2)
        item["student_count"] = int(item["student_count"] or 0)
        by_subject[item["id"]].append(item)
    changes = []
    for subject_id, periods in by_subject.items():
        if len(periods) < 2:
            continue
        current, previous = periods[0], periods[1]
        changes.append({
            "id": subject_id,
            "name": current["name"],
            "code": current["code"],
            "current_term": current["term"],
            "previous_term": previous["term"],
            "current_average": current["average_score"],
            "previous_average": previous["average_score"],
            "change": round(current["average_score"] - previous["average_score"], 2),
            "current_sample": current["student_count"],
            "previous_sample": previous["student_count"],
            "source_updated_at": max(
                value for value in (current.get("source_updated_at"), previous.get("source_updated_at"))
                if value is not None
            ) if current.get("source_updated_at") or previous.get("source_updated_at") else None,
        })
    changes.sort(key=lambda item: (-item["change"], item["name"].casefold()))
    changes = changes[:query.limit]
    if not changes:
        return AssistantResponse(
            outcome=AssistantOutcome.INSUFFICIENT_EVIDENCE,
            answer="I couldn't find two comparable published terms for any subject in your authorized scope.",
            scope=envelope.public_scope(),
        )
    obs = observation(
        kind="subject_trend", entity="subject", facts={"items": changes},
        source="Edvatiq published assessment scores by academic term",
        source_timestamp=max(
            (item["source_updated_at"] for item in changes if item.get("source_updated_at")),
            default=None,
        ),
        sample_size=len(changes), population_size=population,
        definitions={"improvement": "change in normalized average score across the latest two comparable published terms"},
        authorized_scope=envelope.scope_label(population),
    )
    leader = changes[0]
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS,
        answer=(
            f"{leader['name']} shows the largest verified subject-average improvement at "
            f"{leader['change']:+.2f} percentage points across the latest two comparable published terms."
        ),
        artifacts=[Artifact(
            id=identifier("artifact"), type="ranking", title="Subject improvement",
            data={"items": changes, "authorized_population": population},
            evidence_ids=[obs.id],
            security=security(
                permissions=("college.assessments.view",), domains=("assessments",),
                entity_ids=(item["id"] for item in changes), scope={"population": population},
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _student_subject_trend_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
    definitions: dict,
    scope_ids: set[str] | None,
    *,
    background: bool = False,
) -> AssistantResponse:
    score_percent = case(
        (
            and_(CollegeAssessmentScore.marks_awarded.is_not(None), CollegeAssessment.max_marks > 0),
            CollegeAssessmentScore.marks_awarded * 100 / CollegeAssessment.max_marks,
        ),
        else_=CollegeAssessmentScore.calculated_score,
    )
    pass_percent = case(
        (
            and_(CollegeAssessmentComponent.pass_marks.is_not(None), CollegeAssessment.max_marks > 0),
            CollegeAssessmentComponent.pass_marks * 100 / CollegeAssessment.max_marks,
        ),
        else_=Decimal(str(definitions["subject_weak_percent"])),
    )
    statement = select(
        CollegeStudentProfile.id.label("student_id"),
        func.trim(Client.first_name + literal(" ") + Client.last_name).label("student"),
        CollegeCourse.id.label("subject_id"), CollegeCourse.name.label("subject"),
        CollegeTerm.id.label("term_id"), CollegeTerm.name.label("term"),
        CollegeTerm.starts_on.label("term_starts_on"),
        func.avg(score_percent).label("score_percent"),
        func.avg(pass_percent).label("pass_percent"),
        func.max(CollegeAssessmentScore.updated_at).label("source_updated_at"),
    ).select_from(CollegeAssessmentScore).join(
        CollegeStudentProfile,
        CollegeStudentProfile.id == CollegeAssessmentScore.student_profile_id,
    ).join(
        Client, Client.id == CollegeStudentProfile.client_id,
    ).join(
        CollegeAssessment, CollegeAssessment.id == CollegeAssessmentScore.assessment_id,
    ).join(
        CollegeCourseOffering, CollegeCourseOffering.id == CollegeAssessment.offering_id,
    ).join(
        CollegeCourse, CollegeCourse.id == CollegeCourseOffering.course_id,
    ).join(
        CollegeTerm, CollegeTerm.id == CollegeCourseOffering.term_id,
    ).outerjoin(
        CollegeAssessmentComponent,
        CollegeAssessmentComponent.id == CollegeAssessment.scheme_component_id,
    ).where(
        CollegeAssessmentScore.organization_id == envelope.organization_id,
        CollegeStudentProfile.organization_id == envelope.organization_id,
        CollegeAssessment.organization_id == envelope.organization_id,
        CollegeCourseOffering.organization_id == envelope.organization_id,
        CollegeCourse.organization_id == envelope.organization_id,
        CollegeTerm.organization_id == envelope.organization_id,
        CollegeAssessment.status == "published",
        score_percent.is_not(None),
    ).group_by(
        CollegeStudentProfile.id, Client.first_name, Client.last_name,
        CollegeCourse.id, CollegeCourse.name,
        CollegeTerm.id, CollegeTerm.name, CollegeTerm.starts_on,
    )
    if query.requested_analysis == "consistent_core_subject_weakness":
        statement = statement.where(CollegeCourse.course_type == "core")
    if scope_ids is not None:
        statement = statement.where(CollegeStudentProfile.id.in_(scope_ids))

    population = int(db.scalar(statement.with_only_columns(
        func.count(func.distinct(CollegeStudentProfile.id)),
    ).group_by(None).order_by(None)) or 0)
    row_limit = 50000 if background else 5000
    period_rows = list(db.execute(statement.order_by(
        CollegeStudentProfile.id,
        CollegeCourse.id,
        CollegeTerm.starts_on.desc().nullslast(),
        CollegeTerm.id,
    ).limit(row_limit + 1)).all())
    if len(period_rows) > row_limit:
        return AssistantResponse(
            outcome=AssistantOutcome.UNAVAILABLE if background else AssistantOutcome.PROCESSING,
            answer=(
                "This student-subject history exceeds the background safety limit. Narrow the class, department, or subject."
                if background else
                "This student-subject history exceeds the interactive limit and has been queued for background analysis."
            ),
            artifacts=[] if background else [Artifact(
                id=identifier("artifact"), type="processing", title="Student-subject analysis queued",
                data={"authorized_population": population, "period_limit": row_limit},
                security=security(
                    permissions=("college.assessments.view",),
                    domains=("students", "assessments"),
                    scope={"population": population},
                ),
            )], scope=envelope.public_scope(),
        )

    histories: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in period_rows:
        item = dict(row._mapping)
        if item["score_percent"] is None:
            continue
        item["score_percent"] = round(float(item["score_percent"]), 2)
        item["pass_percent"] = round(float(item["pass_percent"]), 2)
        histories[(item["student_id"], item["subject_id"])].append(item)

    by_student: dict[str, dict] = {}
    for periods in histories.values():
        if len(periods) < 2:
            continue
        current, previous = periods[0], periods[1]
        change = round(current["score_percent"] - previous["score_percent"], 2)
        if query.requested_analysis == "consistent_core_subject_weakness":
            if not all(
                period["score_percent"] < period["pass_percent"]
                for period in (current, previous)
            ):
                continue
        elif not (
            previous["score_percent"] < previous["pass_percent"] and change > 0
        ):
            continue
        student = by_student.setdefault(current["student_id"], {
            "id": current["student_id"], "name": current["student"],
            "subjects": [], "weak_subject_count": 0, "best_improvement": None,
            "profile_ref": {"kind": "student", "id": current["student_id"]},
        })
        student["subjects"].append({
            "id": current["subject_id"], "name": current["subject"],
            "current_term": current["term"], "previous_term": previous["term"],
            "current_score": current["score_percent"],
            "previous_score": previous["score_percent"],
            "current_pass_mark": current["pass_percent"],
            "previous_pass_mark": previous["pass_percent"],
            "change": change,
        })
        student["weak_subject_count"] += 1
        student["best_improvement"] = max(
            change, student["best_improvement"] if student["best_improvement"] is not None else change,
        )

    results = list(by_student.values())
    if query.requested_analysis == "consistent_core_subject_weakness":
        results.sort(key=lambda item: (-item["weak_subject_count"], item["name"].casefold()))
        title = "Consistent core-subject support needs"
        definition = (
            "student-subject average below its configured pass mark, or the governed fallback, "
            "in each of the latest two comparable published terms"
        )
    else:
        results.sort(key=lambda item: (-(item["best_improvement"] or 0), item["name"].casefold()))
        title = "Improvement in previously difficult subjects"
        definition = (
            "positive score change across the latest two comparable published terms where the previous-term "
            "average was below its configured pass mark, or the governed fallback"
        )
    results = results[:query.limit]
    for item in results:
        item["subjects"].sort(
            key=lambda subject: subject["change"],
            reverse=query.requested_analysis != "consistent_core_subject_weakness",
        )
        item["subjects"] = item["subjects"][:10]
    if not results:
        return AssistantResponse(
            outcome=AssistantOutcome.INSUFFICIENT_EVIDENCE,
            answer=(
                "I couldn't find students with two comparable published core-subject terms that meet the governed weakness rule."
                if query.requested_analysis == "consistent_core_subject_weakness" else
                "I couldn't find a previously below-pass subject with a positive change across two comparable published terms."
            ),
            scope=envelope.public_scope(),
        )
    obs = observation(
        kind=query.requested_analysis or "student_subject_change", entity="student",
        facts={"items": results}, source="Edvatiq published assessment scores by academic term",
        source_timestamp=max(
            (row.source_updated_at for row in period_rows if row.source_updated_at),
            default=None,
        ),
        sample_size=len(results), population_size=population,
        definitions={
            "weak subject": f"configured pass mark when available, otherwise {definitions['subject_weak_percent']:g}%",
            "analysis": definition,
        },
        authorized_scope=envelope.scope_label(population),
    )
    leader = results[0]
    answer = (
        f"{leader['name']} has the most consistently below-pass core subjects ({leader['weak_subject_count']}) "
        "across the latest two comparable published terms in your authorized scope."
        if query.requested_analysis == "consistent_core_subject_weakness" else
        f"{leader['name']} has the largest verified improvement in a previously below-pass subject "
        f"({leader['best_improvement']:+.2f} percentage points)."
    )
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS, answer=answer,
        artifacts=[Artifact(
            id=identifier("artifact"), type="ranking", title=title,
            data={"items": results, "authorized_population": population},
            evidence_ids=[obs.id],
            security=security(
                permissions=("college.assessments.view",),
                domains=("students", "assessments"),
                entity_ids=(item["id"] for item in results),
                scope={"population": population},
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _company_predicates(query: SemanticQuery) -> list:
    predicates = []
    for ref in query.entities:
        if ref.kind == "company" and ref.id:
            predicates.append(CollegePlacementCompany.id == ref.id)
        elif ref.kind == "company" and ref.label:
            predicates.append(
                func.lower(CollegePlacementCompany.name).contains(ref.label.casefold())
            )
    return predicates


def _apply_company_student_filters(statement, query: SemanticQuery):
    for item in query.filters:
        values = item.value if isinstance(item.value, list) else [item.value]
        if item.field == "student_department":
            statement = statement.where(or_(*[
                or_(
                    func.lower(CollegeDepartment.name).contains(str(value).casefold()),
                    func.lower(CollegeDepartment.code) == str(value).casefold(),
                ) for value in values
            ]))
        elif item.field == "student_cohort":
            statement = statement.where(or_(*[
                or_(
                    func.lower(CollegeCohort.name).contains(str(value).casefold()),
                    func.lower(CollegeCohort.code).contains(str(value).casefold()),
                ) for value in values
            ]))
        elif item.field == "student_section":
            statement = statement.where(
                func.lower(CollegeCohort.section).in_([str(value).casefold() for value in values]),
            )
    return statement


def _company_selected_students_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
    scope_ids: set[str] | None,
    *,
    background: bool = False,
) -> AssistantResponse:
    if "college.students.view" not in envelope.permissions:
        raise AccessViolation(
            AssistantOutcome.ACCESS_LIMITED,
            "This comparison needs access to student profiles and placement records.",
            missing=("college.students.view",),
        )
    statement = select(
        CollegePlacementCompany.id.label("company_id"),
        CollegePlacementCompany.name.label("company"),
        CollegeStudentProfile.id.label("student_id"),
        func.trim(Client.first_name + literal(" ") + Client.last_name).label("student"),
        CollegeDepartment.name.label("department"),
        CollegeCohort.name.label("cohort"),
        CollegePlacementApplication.outcome.label("outcome"),
        CollegePlacementApplication.updated_at.label("source_updated_at"),
    ).select_from(CollegePlacementApplication).join(
        CollegePlacementOpportunity,
        CollegePlacementOpportunity.id == CollegePlacementApplication.opportunity_id,
    ).join(
        CollegePlacementCompany,
        CollegePlacementCompany.id == CollegePlacementOpportunity.company_id,
    ).join(
        CollegeStudentProfile,
        CollegeStudentProfile.id == CollegePlacementApplication.student_profile_id,
    ).join(
        Client, Client.id == CollegeStudentProfile.client_id,
    ).join(
        CollegeProgram, CollegeProgram.id == CollegeStudentProfile.program_id,
    ).join(
        CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id,
    ).join(
        CollegeCohort, CollegeCohort.id == CollegeStudentProfile.cohort_id,
    ).where(
        CollegePlacementApplication.organization_id == envelope.organization_id,
        CollegePlacementOpportunity.organization_id == envelope.organization_id,
        CollegePlacementCompany.organization_id == envelope.organization_id,
        CollegeStudentProfile.organization_id == envelope.organization_id,
        CollegePlacementApplication.outcome.in_(("selected", "offered", "joined")),
    )
    if scope_ids is not None:
        statement = statement.where(CollegeStudentProfile.id.in_(scope_ids))
    company_predicates = _company_predicates(query)
    if company_predicates:
        statement = statement.where(or_(*company_predicates))
    statement = _apply_company_student_filters(statement, query)
    row_limit = 50000 if background else 5000
    rows = list(db.execute(statement.order_by(
        CollegePlacementCompany.name, CollegeStudentProfile.id,
        CollegePlacementApplication.updated_at.desc(),
    ).limit(row_limit + 1)).all())
    if len(rows) > row_limit:
        return AssistantResponse(
            outcome=AssistantOutcome.UNAVAILABLE if background else AssistantOutcome.PROCESSING,
            answer=(
                "This selected-student comparison exceeds the background safety limit. Narrow the companies or student population."
                if background else
                "This selected-student comparison exceeds the interactive limit and has been queued."
            ),
            scope=envelope.public_scope(),
        )
    grouped: dict[str, dict] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        item = dict(row._mapping)
        key = (item["company_id"], item["student_id"])
        if key in seen:
            continue
        seen.add(key)
        group = grouped.setdefault(item["company_id"], {
            "id": item["company_id"], "company": item["company"],
            "selection_count": 0, "students": [],
        })
        group["selection_count"] += 1
        if len(group["students"]) < 100:
            group["students"].append({
                "id": item["student_id"], "name": item["student"],
                "department": item["department"], "cohort": item["cohort"],
                "outcome": item["outcome"],
                "profile_ref": {"kind": "student", "id": item["student_id"]},
            })
    results = sorted(
        grouped.values(), key=lambda item: (-item["selection_count"], item["company"].casefold()),
    )[:query.limit]
    if not results:
        return AssistantResponse(
            outcome=AssistantOutcome.EMPTY,
            answer="I found no selected students for those companies in your authorized scope.",
            scope=envelope.public_scope(),
        )
    distinct_students = {student_id for _company_id, student_id in seen}
    obs = observation(
        kind="selected_students_by_company", entity="company", facts={"groups": results},
        source="Edvatiq placement applications",
        source_timestamp=max((row.source_updated_at for row in rows), default=None),
        sample_size=len(distinct_students), population_size=len(distinct_students),
        definitions={"selected": "application outcome is selected, offered, or joined"},
        authorized_scope=envelope.scope_label(len(distinct_students)),
    )
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS,
        answer=(
            f"I compared {len(results)} companies across {len(distinct_students)} distinct selected students "
            "in your authorized placement scope."
        ),
        artifacts=[Artifact(
            id=identifier("artifact"), type="comparison", title="Selected students by company",
            data={"items": results, "student_count": len(distinct_students)},
            evidence_ids=[obs.id],
            security=security(
                permissions=("college.students.view", "college.placements.view"),
                domains=("students", "placements"),
                entity_ids=(item["id"] for item in results),
                entity_refs=(
                    [
                        {"kind": "company", "id": item["id"], "label": item["company"]}
                        for item in results
                    ]
                    + [
                        {"kind": "student", "id": student["id"], "label": student["name"]}
                        for item in results for student in item["students"]
                    ]
                ),
                scope={"population": len(distinct_students)},
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _company_population_match_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
    scope_ids: set[str] | None,
    *,
    background: bool = False,
) -> AssistantResponse:
    relation_fields = {
        "student_department": "department",
        "student_cohort": "cohort",
        "student_section": "section",
    }
    student_filters = [QueryFilter(
        field=relation_fields[item.field], operator=item.operator, value=item.value,
    ) for item in query.filters if item.field in relation_fields]
    translated = SemanticQuery(
        goal=QueryGoal.MATCH,
        entity="student",
        fields=[
            "id", "name", "department", "program", "cohort", "graduation_year",
            "match_percent", "eligibility_coverage", "placement_status",
        ],
        filters=student_filters,
        entities=[item for item in query.entities if item.kind == "company"],
        limit=query.limit,
        requested_analysis="company_population_match",
    )
    return _student_eligibility_response(
        db, translated, envelope, scope_ids, background=background,
    )


def _company_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
    scope_ids: set[str] | None,
    *,
    background: bool = False,
) -> AssistantResponse:
    if query.requested_analysis == "eligibility_requirements":
        return _company_requirements_response(db, query, envelope)
    if query.requested_analysis == "selected_students_by_company":
        return _company_selected_students_response(
            db, query, envelope, scope_ids, background=background,
        )
    if query.requested_analysis == "company_population_match":
        return _company_population_match_response(
            db, query, envelope, scope_ids, background=background,
        )
    selected = CollegePlacementApplication.outcome.in_(("selected", "offered", "joined"))
    eligible = or_(
        CollegePlacementApplication.eligibility_override_status == "eligible",
        and_(
            CollegePlacementApplication.eligibility_override_status.is_(None),
            CollegePlacementApplication.eligibility_status == "eligible",
        ),
    )
    application_join = and_(
        CollegePlacementApplication.opportunity_id == CollegePlacementOpportunity.id,
        CollegePlacementApplication.organization_id == envelope.organization_id,
    )
    if scope_ids is not None:
        application_join = and_(application_join, CollegePlacementApplication.student_profile_id.in_(scope_ids))
    statement = (
        select(
            CollegePlacementCompany.id.label("id"), CollegePlacementCompany.name.label("name"),
            func.count(func.distinct(case((selected, CollegePlacementApplication.student_profile_id), else_=None))).label("selection_count"),
            func.count(func.distinct(case((eligible, CollegePlacementApplication.student_profile_id), else_=None))).label("eligible_count"),
            func.count(func.distinct(CollegePlacementApplication.student_profile_id)).label("participant_count"),
            func.avg(CollegePlacementOffer.package_paise).label("average_package"),
            func.max(CollegePlacementOffer.package_paise).label("highest_package"),
            func.max(CollegePlacementCompany.updated_at).label("source_updated_at"),
        )
        .select_from(CollegePlacementCompany)
        .outerjoin(CollegePlacementOpportunity, and_(
            CollegePlacementOpportunity.company_id == CollegePlacementCompany.id,
            CollegePlacementOpportunity.organization_id == envelope.organization_id,
        ))
        .outerjoin(CollegePlacementApplication, application_join)
        .outerjoin(CollegeStudentProfile, and_(
            CollegeStudentProfile.id == CollegePlacementApplication.student_profile_id,
            CollegeStudentProfile.organization_id == envelope.organization_id,
        ))
        .outerjoin(CollegeProgram, CollegeProgram.id == CollegeStudentProfile.program_id)
        .outerjoin(CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id)
        .outerjoin(CollegeCohort, CollegeCohort.id == CollegeStudentProfile.cohort_id)
        .outerjoin(CollegePlacementOffer, and_(
            CollegePlacementOffer.application_id == CollegePlacementApplication.id,
            CollegePlacementOffer.organization_id == envelope.organization_id,
        ))
        .where(CollegePlacementCompany.organization_id == envelope.organization_id)
        .group_by(CollegePlacementCompany.id, CollegePlacementCompany.name)
    )
    company_conditions = _company_predicates(query)
    if company_conditions:
        statement = statement.where(or_(*company_conditions))
    for item in query.filters:
        if item.field == "name":
            statement = _apply_filter(statement, CollegePlacementCompany.name, item.operator, item.value)
    statement = _apply_company_student_filters(statement, query)
    rows = []
    for row in db.execute(statement.limit(500)).all():
        item = dict(row._mapping)
        eligible_count = int(item["eligible_count"] or 0)
        selection_count = int(item["selection_count"] or 0)
        item.update({
            "selection_count": selection_count,
            "eligible_count": eligible_count,
            "participant_count": int(item["participant_count"] or 0),
            "selection_rate": round(selection_count * 100 / eligible_count, 2) if eligible_count else None,
            "average_package": round(float(item["average_package"]), 2) if item["average_package"] is not None else None,
        })
        rows.append({key: json_value(value) for key, value in item.items()})
    if query.requested_analysis == "recruiting_companies":
        rows = [item for item in rows if item["selection_count"] > 0]
    sort_field = query.sort[0].field if query.sort else (
        "highest_package" if "package" in (query.requested_analysis or "") else "selection_count"
    )
    reverse = not query.sort or query.sort[0].direction == "desc"
    if reverse:
        rows.sort(key=lambda item: (
            item.get(sort_field) is None,
            -(item.get(sort_field) if item.get(sort_field) is not None else -math.inf),
            item["name"].casefold(),
        ))
    else:
        rows.sort(key=lambda item: (
            item.get(sort_field) is None,
            item.get(sort_field) if item.get(sort_field) is not None else math.inf,
            item["name"].casefold(),
        ))
    rows = rows[:query.limit]
    if not rows:
        return AssistantResponse(
            outcome=AssistantOutcome.NOT_FOUND if query.entities else AssistantOutcome.EMPTY,
            answer="I found no matching placement companies in your authorized scope.",
            scope=envelope.public_scope(),
        )
    obs = observation(
        kind="company_placement_performance", entity="company", facts={"items": rows},
        source="Edvatiq placement applications and offers",
        sample_size=sum(item["participant_count"] for item in rows), population_size=len(rows),
        definitions={"selection rate": "selected, offered, or joined students divided by eligible applications in the authorized scope"},
        authorized_scope=envelope.scope_label(),
    )
    leader = rows[0]
    answer = f"{leader['name']} leads by {sort_field.replace('_', ' ')} in your authorized placement records."
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS, answer=answer,
        artifacts=[Artifact(
            id=identifier("artifact"), type="ranking" if query.goal == QueryGoal.RANK else "comparison",
            title="Company placement performance", data={"items": rows, "sort_field": sort_field},
            evidence_ids=[obs.id],
            security=security(
                permissions=("college.placements.view",),
                domains=(
                    "placements", *(["students"] if any(
                        item.field.startswith("student_") for item in query.filters
                    ) else []),
                ),
                entity_ids=(item["id"] for item in rows),
                scope={"population": sum(item["participant_count"] for item in rows)},
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _company_requirements_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
) -> AssistantResponse:
    statement = select(
        CollegePlacementCompany.id.label("company_id"),
        CollegePlacementCompany.name.label("company"),
        CollegePlacementOpportunity.id.label("opportunity_id"),
        CollegePlacementOpportunity.title.label("opportunity"),
        CollegePlacementOpportunity.opportunity_type.label("opportunity_type"),
        CollegePlacementOpportunity.eligibility_rules.label("requirements"),
        CollegePlacementOpportunity.updated_at.label("source_updated_at"),
    ).join(
        CollegePlacementOpportunity,
        CollegePlacementOpportunity.company_id == CollegePlacementCompany.id,
    ).where(
        CollegePlacementCompany.organization_id == envelope.organization_id,
        CollegePlacementOpportunity.organization_id == envelope.organization_id,
        CollegePlacementOpportunity.status.in_(("published", "active")),
    )
    company_conditions = []
    for ref in query.entities:
        if ref.kind != "company":
            continue
        if ref.id:
            company_conditions.append(CollegePlacementCompany.id == ref.id)
        elif ref.label:
            company_conditions.append(
                func.lower(CollegePlacementCompany.name).contains(ref.label.casefold())
            )
    if company_conditions:
        statement = statement.where(or_(*company_conditions))
    rows = []
    unsupported = set()
    for row in db.execute(statement.limit(200)).all():
        item = dict(row._mapping)
        requirements = dict(item.get("requirements") or {})
        if item.get("opportunity_type") == "internship":
            requirements["require_fee_clearance"] = True
        item.pop("opportunity_type", None)
        unsupported.update(set(requirements) - ELIGIBILITY_RULE_KEYS)
        item["requirements"] = {
            key: json_value(value) for key, value in requirements.items()
            if key in ELIGIBILITY_RULE_KEYS
        }
        rows.append({key: json_value(value) for key, value in item.items()})
    if not rows:
        return AssistantResponse(
            outcome=AssistantOutcome.EMPTY,
            answer="I found no active placement opportunities with requirements in your authorized scope.",
            scope=envelope.public_scope(),
        )
    obs = observation(
        kind="company_eligibility_requirements", entity="company",
        facts={"items": rows, "unsupported_rule_keys": sorted(unsupported)},
        source="Edvatiq reviewed placement opportunity rules",
        source_timestamp=max(
            (item.get("source_updated_at") for item in rows if item.get("source_updated_at")),
            default=None,
        ),
        sample_size=len(rows), population_size=len(rows),
        definitions={
            "comparison": "requirements are shown directly; heterogeneous rules are not converted into an invented strictness score",
        },
        authorized_scope=envelope.scope_label(),
    )
    return AssistantResponse(
        outcome=AssistantOutcome.INSUFFICIENT_EVIDENCE,
        answer=(
            "I can show each reviewed eligibility rule, but I cannot honestly rank which company has the "
            "'highest' criteria without an administrator-configured, non-executable comparison rubric."
        ),
        artifacts=[Artifact(
            id=identifier("artifact"), type="records", title="Company eligibility requirements",
            data={"items": rows, "total": len(rows)}, evidence_ids=[obs.id],
            security=security(
                permissions=("college.placements.view",), domains=("placements",),
                entity_ids=(item["company_id"] for item in rows),
                scope={"population": len(rows)},
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _rule_check(name: str, actual, expected, passes: bool | None) -> dict:
    return {"rule": name, "actual": json_value(actual), "expected": json_value(expected), "passes": passes}


def _evaluate_opportunity_rules(row: dict, rules: dict, clearance: dict | None) -> dict:
    checks = []
    if rules.get("minimum_cgpa") is not None:
        value = row.get("cgpa")
        checks.append(_rule_check(
            "minimum_cgpa", value, rules["minimum_cgpa"],
            None if value is None else float(value) >= float(rules["minimum_cgpa"]),
        ))
    if rules.get("maximum_active_backlogs") is not None:
        value = row.get("active_backlogs")
        checks.append(_rule_check(
            "maximum_active_backlogs", value, rules["maximum_active_backlogs"],
            None if value is None else int(value) <= int(rules["maximum_active_backlogs"]),
        ))
    if rules.get("minimum_attendance") is not None:
        value = row.get("attendance_percent")
        checks.append(_rule_check(
            "minimum_attendance", value, rules["minimum_attendance"],
            None if value is None else float(value) >= float(rules["minimum_attendance"]),
        ))
    if rules.get("minimum_solved") is not None:
        value = row.get("coding_total")
        checks.append(_rule_check(
            "minimum_solved", value, rules["minimum_solved"],
            None if value is None else int(value) >= int(rules["minimum_solved"]),
        ))
    required_skills = {
        str(value).casefold() for value in (rules.get("required_skills") or [])
    }
    if required_skills:
        skills = {
            str(item.get("title") or "").casefold()
            for item in (row.get("skills") or [])
            if item.get("title")
        }
        checks.append(_rule_check(
            "required_skills", sorted(skills), sorted(required_skills),
            None if not skills else required_skills.issubset(skills),
        ))
    if rules.get("require_fee_clearance"):
        status = (clearance or {}).get("status")
        checks.append(_rule_check(
            "fee_clearance", status, "cleared",
            True if status == "cleared" else False if status == "pending" else None,
        ))
    for key, row_key in (
        ("program_ids", "_program_id"),
        ("department_ids", "_department_id"),
        ("cohort_ids", "_cohort_id"),
    ):
        values = {str(value) for value in (rules.get(key) or [])}
        if key == "cohort_ids":
            values.update(str(value) for value in (rules.get("batch_ids") or []))
        if values:
            actual = row.get(row_key)
            checks.append(_rule_check(
                key, actual, sorted(values),
                None if actual is None else str(actual) in values,
            ))
    years = {int(value) for value in (rules.get("graduation_years") or [])}
    if years:
        actual = row.get("graduation_year")
        checks.append(_rule_check(
            "graduation_years", actual, sorted(years),
            None if actual is None else int(actual) in years,
        ))
    status = (
        "ineligible" if any(item["passes"] is False for item in checks)
        else "needs_review" if any(item["passes"] is None for item in checks)
        else "eligible"
    )
    known = sum(item["passes"] is not None for item in checks)
    passed = sum(item["passes"] is True for item in checks)
    total = len(checks)
    return {
        "status": status,
        "checks": checks,
        "coverage_percent": round(known * 100 / total, 1) if total else 100.0,
        "match_percent": round(passed * 100 / total, 1) if total else None,
    }


def _python_filter(value, operator: FilterOperator, expected) -> bool:
    if operator == FilterOperator.EQ:
        return value == expected
    if operator == FilterOperator.NE:
        return value != expected
    if value is None:
        return False
    if operator == FilterOperator.GT:
        return value > expected
    if operator == FilterOperator.GTE:
        return value >= expected
    if operator == FilterOperator.LT:
        return value < expected
    if operator == FilterOperator.LTE:
        return value <= expected
    if operator == FilterOperator.IN:
        return value in (expected if isinstance(expected, list) else [expected])
    if operator == FilterOperator.NOT_IN:
        return value not in (expected if isinstance(expected, list) else [expected])
    return True


def _student_eligibility_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
    scope_ids: set[str] | None,
    *,
    background: bool = False,
) -> AssistantResponse:
    now = datetime.now(timezone.utc)
    opportunity_statement = select(
        CollegePlacementOpportunity, CollegePlacementCompany,
    ).join(
        CollegePlacementCompany,
        CollegePlacementCompany.id == CollegePlacementOpportunity.company_id,
    ).where(
        CollegePlacementOpportunity.organization_id == envelope.organization_id,
        CollegePlacementCompany.organization_id == envelope.organization_id,
        CollegePlacementOpportunity.status.in_(("published", "active")),
        or_(
            CollegePlacementOpportunity.deadline_at.is_(None),
            CollegePlacementOpportunity.deadline_at >= now,
        ),
    )
    company_refs = [item for item in query.entities if item.kind == "company"]
    company_conditions = []
    for ref in company_refs:
        if ref.id:
            company_conditions.append(CollegePlacementCompany.id == ref.id)
        elif ref.label:
            company_conditions.append(
                func.lower(CollegePlacementCompany.name).contains(ref.label.casefold())
            )
    if company_conditions:
        opportunity_statement = opportunity_statement.where(or_(*company_conditions))
    for item in query.filters:
        if item.field == "opportunity_package_max":
            opportunity_statement = _apply_filter(
                opportunity_statement,
                CollegePlacementOpportunity.package_max_paise,
                item.operator,
                item.value,
            )
    opportunity_limit = 500 if background else 100
    opportunities = list(db.execute(
        opportunity_statement.order_by(
            CollegePlacementOpportunity.drive_at.asc().nullslast(),
            CollegePlacementOpportunity.id,
        ).limit(opportunity_limit + 1)
    ).all())
    if len(opportunities) > opportunity_limit:
        return AssistantResponse(
            outcome=AssistantOutcome.PROCESSING if not background else AssistantOutcome.UNAVAILABLE,
            answer=(
                "This eligibility analysis has too many active opportunities for the safety limit. "
                "Narrow it to a company or drive."
            ),
            artifacts=[Artifact(
                id=identifier("artifact"), type="processing", title="Eligibility analysis needs a narrower scope",
                data={"opportunity_limit": opportunity_limit},
                security=security(
                    permissions=("college.placements.view",), domains=("placements",),
                ),
            )] if not background else [],
            scope=envelope.public_scope(),
        )
    if not opportunities:
        return AssistantResponse(
            outcome=AssistantOutcome.NOT_FOUND if company_refs else AssistantOutcome.EMPTY,
            answer="I found no current structured placement opportunities in your authorized scope.",
            scope=envelope.public_scope(),
        )

    rules_by_opportunity = {
        opportunity.id: opportunity_eligibility_rules(opportunity)
        for opportunity, _company in opportunities
    }
    unsupported = {
        key for rules in rules_by_opportunity.values()
        for key in set(rules) - ELIGIBILITY_RULE_KEYS
    }
    if unsupported:
        return AssistantResponse(
            outcome=AssistantOutcome.CONFIGURATION_REQUIRED,
            answer=(
                "One or more active opportunities use eligibility rules that are not registered in the "
                "approved semantic catalog. Review those rules before using them in AI analysis."
            ),
            artifacts=[Artifact(
                id=identifier("artifact"), type="notice", title="Eligibility rule review required",
                data={"unsupported_rule_keys": sorted(unsupported)},
                security=security(
                    permissions=("college.placements.view",), domains=("placements",),
                ),
            )], scope=envelope.public_scope(),
        )

    rule_keys = set().union(*(set(rules) for rules in rules_by_opportunity.values()))
    domain_requirements = {"placements"}
    fields = {
        "id", "name", "department", "program", "cohort", "graduation_year",
        "placement_status",
    }
    permission_requirements = {"college.placements.view"}
    if rule_keys & {"minimum_cgpa", "maximum_active_backlogs"}:
        fields.update(("cgpa", "active_backlogs"))
        domain_requirements.add("assessments")
        permission_requirements.add("college.assessments.view")
    if "minimum_attendance" in rule_keys:
        fields.add("attendance_percent")
        domain_requirements.add("attendance")
        permission_requirements.add("college.attendance.view")
    if "minimum_solved" in rule_keys:
        fields.add("coding_total")
        domain_requirements.add("coding")
        permission_requirements.add("college.coding.view")
    if "required_skills" in rule_keys:
        fields.add("skills")
        domain_requirements.add("readiness")
        permission_requirements.add("college.readiness.view")
    needs_clearance = "require_fee_clearance" in rule_keys
    if needs_clearance:
        domain_requirements.add("clearance")
        permission_requirements.add("college.clearance.view")
    missing_permissions = permission_requirements - envelope.permissions
    if missing_permissions:
        raise AccessViolation(
            AssistantOutcome.ACCESS_LIMITED,
            "This eligibility analysis needs additional authorized work areas.",
            missing=missing_permissions,
        )
    dynamic_scope = envelope.student_scope(domain_requirements)
    if scope_ids is None:
        authorized_ids = dynamic_scope
    elif dynamic_scope is None:
        authorized_ids = scope_ids
    else:
        authorized_ids = scope_ids & dynamic_scope

    computed_fields = {
        "eligible_company_count", "match_percent", "eligibility_coverage",
        "opportunity_package_max",
    }
    base_query = query.model_copy(update={
        "fields": sorted(fields),
        "filters": [item for item in query.filters if item.field not in computed_fields],
        "metrics": [], "group_by": [], "sort": [], "limit": 100,
    })
    row_limit = 50000 if background else 1000
    rows, total, _policy = _student_dataset(
        db, base_query, fields, envelope, authorized_ids,
        limit=row_limit, hard_limit=row_limit,
    )
    if total > row_limit:
        return AssistantResponse(
            outcome=AssistantOutcome.PROCESSING if not background else AssistantOutcome.UNAVAILABLE,
            answer=(
                "This eligibility population exceeds the authorized analysis safety limit. "
                "The interactive request has been queued for background processing."
                if not background else
                "This eligibility population exceeds the background safety limit. Narrow the student scope."
            ),
            artifacts=[Artifact(
                id=identifier("artifact"), type="processing", title="Eligibility analysis queued",
                data={"authorized_population": total, "query": query.model_dump(mode="json")},
                security=security(
                    permissions=tuple(permission_requirements),
                    domains=tuple(domain_requirements), scope={"population": total},
                ),
            )] if not background else [],
            scope=envelope.public_scope(),
        )
    if not rows:
        return AssistantResponse(
            outcome=AssistantOutcome.EMPTY,
            answer="I found no students in the authorized population for this eligibility analysis.",
            scope=envelope.public_scope(),
        )

    student_ids = [row["id"] for row in rows]
    clearances = fee_clearance_by_student(
        db, envelope.organization_id, student_ids,
    ) if needs_clearance else {}
    opportunity_ids = [opportunity.id for opportunity, _company in opportunities]
    applications = db.execute(select(CollegePlacementApplication).where(
        CollegePlacementApplication.organization_id == envelope.organization_id,
        CollegePlacementApplication.student_profile_id.in_(student_ids),
        CollegePlacementApplication.opportunity_id.in_(opportunity_ids),
    )).scalars()
    applied = {(item.student_profile_id, item.opportunity_id) for item in applications}

    results = []
    for row in rows:
        evaluations = []
        for opportunity, company in opportunities:
            evaluation = _evaluate_opportunity_rules(
                row, rules_by_opportunity[opportunity.id], clearances.get(row["id"]),
            )
            evaluations.append({
                "opportunity_id": opportunity.id,
                "opportunity": opportunity.title,
                "company_id": company.id,
                "company": company.name,
                "package_min_paise": opportunity.package_min_paise,
                "package_max_paise": opportunity.package_max_paise,
                "status": evaluation["status"],
                "coverage_percent": evaluation["coverage_percent"],
                "match_percent": evaluation["match_percent"],
                "applied": (row["id"], opportunity.id) in applied,
                "checks": evaluation["checks"],
            })
        eligible = [item for item in evaluations if item["status"] == "eligible"]
        eligible_not_applied = [item for item in eligible if not item["applied"]]
        scored = [item for item in evaluations if item["match_percent"] is not None]
        best_match = max(scored, key=lambda item: item["match_percent"]) if scored else None
        item = {
            "id": row["id"], "name": row["name"],
            "department": row.get("department"), "program": row.get("program"),
            "cohort": row.get("cohort"), "graduation_year": row.get("graduation_year"),
            "placement_status": row.get("placement_status"),
            "eligible_company_count": len(eligible),
            "eligibility_coverage": round(
                sum(value["coverage_percent"] for value in evaluations) / len(evaluations), 1,
            ),
            "match_percent": best_match["match_percent"] if best_match else None,
            "best_match": best_match,
            "eligible_not_applied_count": len(eligible_not_applied),
            "opportunities": evaluations,
            "profile_ref": {"kind": "student", "id": row["id"]},
        }
        computed_filters = [
            value for value in query.filters if value.field in computed_fields
        ]
        if computed_filters and not all(
            _python_filter(item.get(value.field), value.operator, value.value)
            for value in computed_filters
        ):
            continue
        if query.requested_analysis == "eligible_not_applied" and not eligible_not_applied:
            continue
        if (
            query.goal == QueryGoal.ELIGIBILITY
            and query.requested_analysis not in {"group_eligibility_count", "group_eligibility_rate"}
            and not computed_filters and not eligible
        ):
            continue
        results.append(item)

    if not results:
        return AssistantResponse(
            outcome=AssistantOutcome.EMPTY,
            answer="No students matched the reviewed opportunity rules in your authorized scope.",
            scope=envelope.public_scope(),
        )
    if query.requested_analysis in {"group_eligibility_count", "group_eligibility_rate"}:
        grouped: dict[str, list[dict]] = defaultdict(list)
        for item in results:
            label = " / ".join(str(item.get(field) or "Unknown") for field in query.group_by)
            grouped[label].append(item)
        group_results = []
        for label, items in grouped.items():
            eligible_students = [item for item in items if item["eligible_company_count"] > 0]
            needs_review = [
                item for item in items
                if not item["eligible_company_count"] and any(
                    opportunity["status"] == "needs_review"
                    for opportunity in item["opportunities"]
                )
            ]
            conclusive = len(items) - len(needs_review)
            group_results.append({
                "group": label,
                "eligible_student_count": len(eligible_students),
                "needs_review_count": len(needs_review),
                "conclusive_student_count": conclusive,
                "student_count": len(items),
                "eligibility_rate": round(len(eligible_students) * 100 / conclusive, 2) if conclusive else None,
                "average_eligible_companies": round(
                    sum(item["eligible_company_count"] for item in items) / len(items), 2,
                ),
            })
        rank_by_count = query.requested_analysis == "group_eligibility_count"
        sort_field = "eligible_student_count" if rank_by_count else "eligibility_rate"
        group_results.sort(key=lambda item: (
            item[sort_field] is None,
            -(item[sort_field] if item[sort_field] is not None else -math.inf),
            item["group"].casefold(),
        ))
        leader = group_results[0]
        conclusive_total = sum(item["conclusive_student_count"] for item in group_results)
        eligible_total = sum(item["eligible_student_count"] for item in group_results)
        needs_review_total = sum(item["needs_review_count"] for item in group_results)
        obs = observation(
            kind="group_placement_eligibility", entity="student",
            facts={"groups": group_results, "opportunity_count": len(opportunities)},
            source="Edvatiq reviewed opportunity rules and verified student evidence",
            source_timestamp=max(
                (opportunity.updated_at for opportunity, _company in opportunities),
                default=None,
            ),
            sample_size=conclusive_total, population_size=total,
            coverage_percent=round(conclusive_total * 100 / total, 1) if total else 0,
            definitions={
                "eligibility rate": "students eligible for at least one current opportunity divided by students with a conclusive evaluation",
                "needs review": "one or more required evidence values are missing; these students are excluded from the rate denominator",
            },
            authorized_scope=envelope.scope_label(total),
        )
        return AssistantResponse(
            outcome=AssistantOutcome.SUCCESS if conclusive_total else AssistantOutcome.INSUFFICIENT_EVIDENCE,
            answer=(
                (
                    f"{leader['group']} has the most currently eligible students at "
                    f"{leader['eligible_student_count']} among conclusive authorized evaluations. "
                    if rank_by_count else
                    f"{leader['group']} has the highest current placement eligibility rate at "
                    f"{leader['eligibility_rate']:.2f}% among conclusive authorized evaluations. "
                ) + f"{needs_review_total} of {total} students still need evidence review."
                if conclusive_total and (rank_by_count or leader["eligibility_rate"] is not None) else
                "No group has enough complete evidence for a conclusive placement eligibility rate."
            ),
            artifacts=[Artifact(
                id=identifier("artifact"), type="comparison", title="Placement eligibility by group",
                data={
                    "items": group_results, "sort_field": sort_field,
                    "eligible_students": eligible_total, "authorized_population": total,
                },
                evidence_ids=[obs.id],
                security=security(
                    permissions=tuple(permission_requirements), domains=tuple(domain_requirements),
                    entity_ids=(item["id"] for item in results), scope={"population": total},
                ),
            )], observations=[obs], scope=envelope.public_scope(),
        )
    if query.requested_analysis == "company_population_match":
        company_students: dict[str, dict] = {}
        for student in results:
            evaluations_by_company: dict[str, list[dict]] = defaultdict(list)
            for evaluation in student["opportunities"]:
                evaluations_by_company[evaluation["company_id"]].append(evaluation)
            for company_id, evaluations in evaluations_by_company.items():
                scored = [
                    value for value in evaluations
                    if value["match_percent"] is not None
                ]
                if not scored:
                    continue
                best = max(scored, key=lambda value: (
                    value["match_percent"], value["coverage_percent"], value["opportunity_id"],
                ))
                company = company_students.setdefault(company_id, {
                    "id": company_id, "company": best["company"],
                    "student_scores": [], "eligible_students": set(),
                    "opportunity_ids": set(),
                })
                company["student_scores"].append({
                    "student_id": student["id"],
                    "match_percent": best["match_percent"],
                    "coverage_percent": best["coverage_percent"],
                })
                company["opportunity_ids"].update(
                    value["opportunity_id"] for value in evaluations
                )
                if any(value["status"] == "eligible" for value in evaluations):
                    company["eligible_students"].add(student["id"])
        company_results = []
        covered_students = set()
        for item in company_students.values():
            scores = item.pop("student_scores")
            covered_students.update(value["student_id"] for value in scores)
            opportunity_ids = item.pop("opportunity_ids")
            eligible_students = item.pop("eligible_students")
            item.update({
                "average_match_percent": round(
                    sum(value["match_percent"] for value in scores) / len(scores), 2,
                ),
                "average_coverage_percent": round(
                    sum(value["coverage_percent"] for value in scores) / len(scores), 2,
                ),
                "student_sample": len(scores),
                "eligible_student_count": len(eligible_students),
                "opportunity_count": len(opportunity_ids),
            })
            company_results.append(item)
        company_results.sort(key=lambda item: (
            -item["average_match_percent"], -item["student_sample"], item["company"].casefold(),
        ))
        company_results = company_results[:query.limit]
        if not company_results:
            return AssistantResponse(
                outcome=AssistantOutcome.INSUFFICIENT_EVIDENCE,
                answer=(
                    "Current opportunities do not contain enough structured requirements to compare "
                    "company matches for the authorized student population."
                ),
                scope=envelope.public_scope(),
            )
        obs = observation(
            kind="company_population_requirement_match", entity="company",
            facts={"items": company_results},
            source="Edvatiq reviewed opportunity rules and verified student evidence",
            source_timestamp=max(
                (opportunity.updated_at for opportunity, _company in opportunities),
                default=None,
            ),
            sample_size=len(covered_students), population_size=total,
            coverage_percent=round(len(covered_students) * 100 / total, 1) if total else 0,
            definitions={
                "company match": "mean of each student's best current structured-opportunity requirement match for that company",
                "match percentage": "passed reviewed requirements divided by all reviewed requirements; not an employment probability",
            },
            authorized_scope=envelope.scope_label(total),
        )
        leader = company_results[0]
        return AssistantResponse(
            outcome=AssistantOutcome.SUCCESS,
            answer=(
                f"{leader['company']} has the strongest structured requirement match at "
                f"{leader['average_match_percent']:.2f}% across {leader['student_sample']} authorized students. "
                "This is an evidence match, not a prediction of hiring success."
            ),
            artifacts=[Artifact(
                id=identifier("artifact"), type="ranking", title="Company requirement match",
                data={"items": company_results, "authorized_population": total},
                evidence_ids=[obs.id],
                security=security(
                    permissions=tuple(permission_requirements), domains=tuple(domain_requirements),
                    entity_ids=(item["id"] for item in company_results), scope={"population": total},
                ),
            )], observations=[obs], scope=envelope.public_scope(),
        )
    if query.goal == QueryGoal.MATCH and not any(
        item["match_percent"] is not None for item in results
    ):
        return AssistantResponse(
            outcome=AssistantOutcome.INSUFFICIENT_EVIDENCE,
            answer=(
                "The selected current opportunities do not contain structured requirements, "
                "so I cannot calculate a defensible student-company match."
            ),
            scope=envelope.public_scope(),
        )
    if query.goal == QueryGoal.MATCH:
        results.sort(key=lambda item: (item["match_percent"] is not None, item["match_percent"] or -math.inf), reverse=True)
    else:
        results.sort(key=lambda item: (-item["eligible_company_count"], item["name"].casefold()))
    matched_total = len(results)
    results = results[:query.limit]
    average_coverage = round(sum(item["eligibility_coverage"] for item in results) / len(results), 1)
    obs = observation(
        kind="student_company_match" if query.goal == QueryGoal.MATCH else "student_eligibility",
        entity="student", facts={"items": results, "opportunity_count": len(opportunities)},
        source="Edvatiq reviewed opportunity rules and verified student evidence",
        source_timestamp=max(
            (opportunity.updated_at for opportunity, _company in opportunities),
            default=None,
        ),
        sample_size=len(results), population_size=total,
        coverage_percent=average_coverage,
        definitions={
            "eligible": "all reviewed requirements pass; missing required evidence produces needs review",
            "match percentage": "passed structured requirements divided by all structured requirements; not an employment probability",
        },
        authorized_scope=envelope.scope_label(total),
    )
    leader = results[0]
    if query.goal == QueryGoal.MATCH:
        answer = (
            f"{leader['name']} has the strongest structured requirement match at "
            f"{leader['match_percent']:.1f}% among {envelope.scope_label(total)}. "
            "This is an evidence match, not a prediction of selection."
        )
    else:
        answer = (
            f"I found {matched_total} matching students in {envelope.scope_label(total)}. "
            f"{leader['name']} is eligible for {leader['eligible_company_count']} current opportunities."
        )
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS,
        answer=answer,
        artifacts=[Artifact(
            id=identifier("artifact"),
            type="ranking" if query.goal == QueryGoal.MATCH or query.sort else "records",
            title="Student eligibility and requirement matches",
            data={"items": results, "total": matched_total, "authorized_population": total},
            evidence_ids=[obs.id],
            security=security(
                permissions=tuple(permission_requirements), domains=tuple(domain_requirements),
                entity_ids=(item["id"] for item in results), scope={"population": total},
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _student_offer_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
    scope_ids: set[str] | None,
    *,
    background: bool = False,
) -> AssistantResponse:
    fields = {
        "id", "name", "department", "program", "cohort",
        "placement_status", "offer_count", "highest_package",
    }
    candidate_query = query.model_copy(update={
        "fields": sorted(fields), "metrics": [], "group_by": [], "sort": [], "limit": 100,
    })
    row_limit = 50000 if background else 5000
    rows, total, _ = _student_dataset(
        db, candidate_query, fields, envelope, scope_ids,
        limit=row_limit, hard_limit=row_limit,
    )
    if total > row_limit:
        return AssistantResponse(
            outcome=AssistantOutcome.UNAVAILABLE if background else AssistantOutcome.PROCESSING,
            answer=(
                "This offer analysis exceeds the background safety limit. Narrow the student population."
                if background else
                "This offer analysis exceeds the interactive limit and has been queued for background processing."
            ),
            artifacts=[] if background else [Artifact(
                id=identifier("artifact"), type="processing", title="Offer analysis queued",
                data={"authorized_population": total, "query": query.model_dump(mode="json")},
                security=security(
                    permissions=("college.placements.view",), domains=("students", "placements"),
                    scope={"population": total},
                ),
            )], scope=envelope.public_scope(),
        )
    if not rows:
        return AssistantResponse(
            outcome=AssistantOutcome.EMPTY,
            answer="I found no students matching that offer rule in your authorized scope.",
            scope=envelope.public_scope(),
        )

    student_ids = [row["id"] for row in rows]
    offer_limit = 100000 if background else 10000
    offer_rows = list(db.execute(select(
        CollegePlacementApplication.student_profile_id.label("student_id"),
        CollegePlacementOffer.id.label("offer_id"),
        CollegePlacementOffer.status.label("status"),
        CollegePlacementOffer.offered_role.label("role"),
        CollegePlacementOffer.package_paise.label("package_paise"),
        CollegePlacementOffer.offered_on.label("offered_on"),
        CollegePlacementOffer.joining_on.label("joining_on"),
        CollegePlacementOffer.updated_at.label("source_updated_at"),
        CollegePlacementCompany.id.label("company_id"),
        CollegePlacementCompany.name.label("company"),
    ).select_from(CollegePlacementOffer).join(
        CollegePlacementApplication,
        CollegePlacementApplication.id == CollegePlacementOffer.application_id,
    ).join(
        CollegePlacementOpportunity,
        CollegePlacementOpportunity.id == CollegePlacementApplication.opportunity_id,
    ).join(
        CollegePlacementCompany,
        CollegePlacementCompany.id == CollegePlacementOpportunity.company_id,
    ).where(
        CollegePlacementOffer.organization_id == envelope.organization_id,
        CollegePlacementApplication.organization_id == envelope.organization_id,
        CollegePlacementOpportunity.organization_id == envelope.organization_id,
        CollegePlacementCompany.organization_id == envelope.organization_id,
        CollegePlacementApplication.student_profile_id.in_(student_ids),
    ).order_by(
        CollegePlacementApplication.student_profile_id,
        CollegePlacementOffer.offered_on.desc().nullslast(),
        CollegePlacementOffer.id,
    ).limit(offer_limit + 1)).all())
    if len(offer_rows) > offer_limit:
        return AssistantResponse(
            outcome=AssistantOutcome.UNAVAILABLE if background else AssistantOutcome.PROCESSING,
            answer=(
                "This offer history exceeds the background safety limit. Narrow the student population."
                if background else
                "This offer history is too large for an interactive answer and has been queued."
            ),
            scope=envelope.public_scope(),
        )

    offers_by_student: dict[str, list[dict]] = defaultdict(list)
    for result in offer_rows:
        item = {key: json_value(value) for key, value in dict(result._mapping).items()}
        offers_by_student[item.pop("student_id")].append(item)
    results = []
    pending_only = query.requested_analysis == "offers_pending_joining"
    for row in rows:
        offers = offers_by_student.get(row["id"], [])
        if pending_only:
            offers = [item for item in offers if item["status"] in {"offered", "accepted"}]
        if not offers:
            continue
        results.append({
            "id": row["id"], "name": row["name"],
            "department": row.get("department"), "program": row.get("program"),
            "cohort": row.get("cohort"), "placement_status": row.get("placement_status"),
            "offer_count": len(offers), "offers": offers,
            "profile_ref": {"kind": "student", "id": row["id"]},
        })
    results.sort(key=lambda item: (-item["offer_count"], item["name"].casefold()))
    matched_total = len(results)
    results = results[:query.limit]
    if not results:
        return AssistantResponse(
            outcome=AssistantOutcome.EMPTY,
            answer=(
                "No students have an offered or accepted offer awaiting joining in your authorized scope."
                if pending_only else
                "No students have matching recorded offers in your authorized scope."
            ),
            scope=envelope.public_scope(),
        )
    obs = observation(
        kind="student_offer_status", entity="student", facts={"items": results},
        source="Edvatiq placement applications and offers",
        source_timestamp=max(
            (
                item.get("source_updated_at")
                for result in results for item in result["offers"]
                if item.get("source_updated_at")
            ),
            default=None,
        ),
        sample_size=matched_total, population_size=total,
        definitions={
            "awaiting joining": "offer status is offered or accepted; joined offers are excluded",
        } if pending_only else {},
        authorized_scope=envelope.scope_label(total),
    )
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS,
        answer=(
            f"I found {matched_total} students with an offered or accepted offer who have not joined yet "
            f"among {envelope.scope_label(total)}."
            if pending_only else
            f"I found {matched_total} students with matching recorded offers among {envelope.scope_label(total)}."
        ),
        artifacts=[Artifact(
            id=identifier("artifact"), type="records", title="Student placement offers",
            data={"items": results, "total": matched_total, "authorized_population": total},
            evidence_ids=[obs.id],
            security=security(
                permissions=("college.placements.view",), domains=("students", "placements"),
                entity_ids=(item["id"] for item in results), scope={"population": total},
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _placement_skill_frequency_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
    scope_ids: set[str] | None,
    *,
    background: bool = False,
) -> AssistantResponse:
    fields = {"id", "name", "placement_status"}
    filters = [item for item in query.filters if item.field != "skills"]
    if not any(item.field == "placement_status" for item in filters):
        filters.append(QueryFilter(
            field="placement_status", operator=FilterOperator.EQ, value="placed",
        ))
    candidate_query = query.model_copy(update={
        "fields": sorted(fields), "filters": filters,
        "metrics": [], "group_by": [], "sort": [], "limit": 100,
    })
    row_limit = 50000 if background else 5000
    rows, total, _ = _student_dataset(
        db, candidate_query, fields, envelope, scope_ids,
        limit=row_limit, hard_limit=row_limit,
    )
    if total > row_limit:
        return AssistantResponse(
            outcome=AssistantOutcome.UNAVAILABLE if background else AssistantOutcome.PROCESSING,
            answer=(
                "This skill-frequency analysis exceeds the background safety limit. Narrow the population."
                if background else
                "This skill-frequency analysis exceeds the interactive limit and has been queued."
            ),
            scope=envelope.public_scope(),
        )
    if not rows:
        return AssistantResponse(
            outcome=AssistantOutcome.EMPTY,
            answer="I found no placed students in the authorized population for this analysis.",
            scope=envelope.public_scope(),
        )
    student_ids = [row["id"] for row in rows]
    evidence = list(db.execute(select(CollegeCareerEvidence).where(
        CollegeCareerEvidence.organization_id == envelope.organization_id,
        CollegeCareerEvidence.student_profile_id.in_(student_ids),
        CollegeCareerEvidence.evidence_type == "skill",
        CollegeCareerEvidence.is_verified.is_(True),
    ).order_by(CollegeCareerEvidence.title, CollegeCareerEvidence.student_profile_id)).scalars())
    students_by_skill: dict[str, set[str]] = defaultdict(set)
    display_names: dict[str, str] = {}
    for item in evidence:
        key = " ".join(item.title.casefold().split())
        if not key:
            continue
        students_by_skill[key].add(item.student_profile_id)
        display_names.setdefault(key, item.title)
    frequencies = [{
        "skill": display_names[key],
        "student_count": len(student_ids_for_skill),
        "share_percent": round(len(student_ids_for_skill) * 100 / total, 2) if total else 0,
    } for key, student_ids_for_skill in students_by_skill.items()]
    frequencies.sort(key=lambda item: (-item["student_count"], item["skill"].casefold()))
    frequencies = frequencies[:query.limit]
    covered_students = len({item.student_profile_id for item in evidence})
    if not frequencies:
        return AssistantResponse(
            outcome=AssistantOutcome.INSUFFICIENT_EVIDENCE,
            answer="The authorized placed-student population has no verified technical-skill evidence.",
            scope=envelope.public_scope(),
        )
    obs = observation(
        kind="placed_student_skill_frequency", entity="student",
        facts={"skills": frequencies},
        source="Edvatiq verified career evidence and placement outcomes",
        source_timestamp=max((item.updated_at for item in evidence), default=None),
        sample_size=covered_students, population_size=total,
        coverage_percent=round(covered_students * 100 / total, 1) if total else 0,
        definitions={
            "frequency": "share of authorized placed students with a verified skill evidence record",
            "interpretation": "descriptive historical frequency; not a cause of placement success",
        },
        authorized_scope=envelope.scope_label(total),
    )
    leader = frequencies[0]
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS,
        answer=(
            f"{leader['skill']} is the most common verified technical skill in this authorized placed-student "
            f"population ({leader['student_count']} of {total}). This is a historical frequency, not evidence of causation."
        ),
        artifacts=[Artifact(
            id=identifier("artifact"), type="ranking", title="Verified skills among placed students",
            data={"items": frequencies, "authorized_population": total},
            evidence_ids=[obs.id],
            security=security(
                permissions=("college.placements.view", "college.readiness.view"),
                domains=("students", "placements", "readiness"),
                scope={"population": total},
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _company_group_selection_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
    scope_ids: set[str] | None,
) -> AssistantResponse:
    selected = CollegePlacementApplication.outcome.in_(("selected", "offered", "joined"))
    eligible = or_(
        CollegePlacementApplication.eligibility_override_status == "eligible",
        and_(
            CollegePlacementApplication.eligibility_override_status.is_(None),
            CollegePlacementApplication.eligibility_status == "eligible",
        ),
    )
    group_columns = []
    if "department" in query.group_by:
        group_columns.append(CollegeDepartment.name)
    if "cohort" in query.group_by:
        group_columns.append(CollegeCohort.name)
    if not group_columns:
        group_columns.append(CollegeDepartment.name)
    statement = select(
        *[column.label(f"group_{index}") for index, column in enumerate(group_columns)],
        func.count(func.distinct(case((eligible, CollegeStudentProfile.id), else_=None))).label("eligible_count"),
        func.count(func.distinct(case((selected, CollegeStudentProfile.id), else_=None))).label("selection_count"),
        func.max(CollegePlacementApplication.updated_at).label("source_updated_at"),
    ).select_from(CollegePlacementApplication).join(
        CollegePlacementOpportunity,
        CollegePlacementOpportunity.id == CollegePlacementApplication.opportunity_id,
    ).join(
        CollegePlacementCompany,
        CollegePlacementCompany.id == CollegePlacementOpportunity.company_id,
    ).join(
        CollegeStudentProfile,
        CollegeStudentProfile.id == CollegePlacementApplication.student_profile_id,
    ).join(
        CollegeProgram, CollegeProgram.id == CollegeStudentProfile.program_id,
    ).join(
        CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id,
    ).join(
        CollegeCohort, CollegeCohort.id == CollegeStudentProfile.cohort_id,
    ).where(
        CollegePlacementApplication.organization_id == envelope.organization_id,
        CollegePlacementOpportunity.organization_id == envelope.organization_id,
        CollegePlacementCompany.organization_id == envelope.organization_id,
        CollegeStudentProfile.organization_id == envelope.organization_id,
    ).group_by(*group_columns)
    if scope_ids is not None:
        statement = statement.where(CollegeStudentProfile.id.in_(scope_ids))
    company_predicates = _company_predicates(query)
    if company_predicates:
        statement = statement.where(or_(*company_predicates))
    for item in query.filters:
        values = item.value if isinstance(item.value, list) else [item.value]
        if item.field == "department":
            statement = statement.where(or_(*[
                or_(
                    func.lower(CollegeDepartment.name).contains(str(value).casefold()),
                    func.lower(CollegeDepartment.code) == str(value).casefold(),
                ) for value in values
            ]))
        elif item.field == "section":
            statement = statement.where(
                func.lower(CollegeCohort.section).in_([str(value).casefold() for value in values]),
            )
    rows = []
    for row in db.execute(statement.limit(500)).all():
        item = dict(row._mapping)
        labels = [item.pop(f"group_{index}") for index in range(len(group_columns))]
        eligible_count = int(item["eligible_count"] or 0)
        selection_count = int(item["selection_count"] or 0)
        rows.append({
            "group": " / ".join(str(value) for value in labels),
            "eligible_count": eligible_count,
            "selection_count": selection_count,
            "selection_rate": round(selection_count * 100 / eligible_count, 2) if eligible_count else None,
            "source_updated_at": json_value(item.get("source_updated_at")),
        })
    rows.sort(key=lambda item: (
        item["selection_rate"] is None,
        -(item["selection_rate"] if item["selection_rate"] is not None else -math.inf),
        item["group"].casefold(),
    ))
    rows = rows[:query.limit]
    if not rows:
        return AssistantResponse(
            outcome=AssistantOutcome.EMPTY,
            answer="I found no eligible placement applications for that company in your authorized groups.",
            scope=envelope.public_scope(),
        )
    obs = observation(
        kind="company_selection_rate_by_group", entity="student", facts={"groups": rows},
        source="Edvatiq placement applications",
        source_timestamp=max(
            (item["source_updated_at"] for item in rows if item.get("source_updated_at")),
            default=None,
        ),
        sample_size=sum(item["eligible_count"] for item in rows),
        population_size=sum(item["eligible_count"] for item in rows),
        definitions={
            "selection rate": "distinct selected, offered, or joined students divided by distinct eligible students for the selected company",
        },
        authorized_scope=envelope.scope_label(sum(item["eligible_count"] for item in rows)),
    )
    leader = rows[0]
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS if leader["selection_rate"] is not None else AssistantOutcome.INSUFFICIENT_EVIDENCE,
        answer=(
            f"{leader['group']} has the highest authorized selection rate for this company at "
            f"{leader['selection_rate']:.2f}%."
            if leader["selection_rate"] is not None else
            "No group has enough eligible applications to calculate a selection rate for this company."
        ),
        artifacts=[Artifact(
            id=identifier("artifact"), type="comparison", title="Company selection rate by group",
            data={"items": rows, "sort_field": "selection_rate"}, evidence_ids=[obs.id],
            security=security(
                permissions=("college.students.view", "college.placements.view"),
                domains=("students", "placements"),
                scope={"population": sum(item["eligible_count"] for item in rows)},
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _placement_analysis_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
    definitions: dict,
    scope_ids: set[str] | None,
    *,
    background: bool = False,
) -> AssistantResponse:
    fields = {"placement_status"}
    domains = {"placements"}
    optional = (
        ("cgpa", "assessments", "college.assessments.view"),
        ("attendance_percent", "attendance", "college.attendance.view"),
        ("readiness_score", "readiness", "college.readiness.view"),
        ("skill_count", "readiness", "college.readiness.view"),
        ("project_count", "readiness", "college.readiness.view"),
        ("certification_count", "readiness", "college.readiness.view"),
    )
    for field, domain, permission in optional:
        if permission in envelope.permissions and envelope.domain_available(domain):
            fields.add(field)
            domains.add(domain)
    analysis_scope = envelope.student_scope(domains)
    if scope_ids is None:
        scope_ids = analysis_scope
    elif analysis_scope is not None:
        scope_ids = scope_ids & analysis_scope
    analysis_query = query.model_copy(update={
        "fields": sorted(fields),
        "filters": [item for item in query.filters if item.field != "placement_status"],
        "sort": [], "metrics": [], "limit": 100,
    })
    row_limit = 50000 if background else 5000
    rows, total, _ = _student_dataset(
        db, analysis_query, fields, envelope, scope_ids,
        limit=row_limit, hard_limit=row_limit,
    )
    if total > row_limit:
        return AssistantResponse(
            outcome=AssistantOutcome.UNAVAILABLE if background else AssistantOutcome.PROCESSING,
            answer=(
                "This placement analysis exceeds the background safety limit. Narrow the population or time range."
                if background else
                "This placement analysis exceeds the interactive limit and has been queued as an authorized background job."
            ),
            artifacts=[] if background else [Artifact(
                id=identifier("artifact"), type="processing", title="Placement analysis queued",
                data={"authorized_population": total},
                security=security(
                    permissions=("college.placements.view",), domains=("placements",),
                    scope={"population": total},
                ),
            )], scope=envelope.public_scope(),
        )
    placed = [row for row in rows if row.get("placement_status") == "placed"]
    unplaced = [row for row in rows if row.get("placement_status") == "unplaced"]
    minimum = int(definitions["minimum_association_sample"])
    if min(len(placed), len(unplaced)) < minimum:
        return AssistantResponse(
            outcome=AssistantOutcome.INSUFFICIENT_EVIDENCE,
            answer=(
                f"The authorized data has {len(placed)} placed and {len(unplaced)} unplaced students. "
                f"At least {minimum} in each group is required for a reliable descriptive comparison."
            ),
            artifacts=[Artifact(
                id=identifier("artifact"), type="notice", title="Insufficient comparison sample",
                data={"placed": len(placed), "unplaced": len(unplaced), "required_per_group": minimum},
                security=security(
                    permissions=("college.placements.view",), domains=("placements",),
                    entity_ids=(row["id"] for row in rows),
                ),
            )], scope=envelope.public_scope(),
        )
    comparison = []
    for field in sorted(fields - {"placement_status"}):
        placed_value, placed_n = _metric_value({
            "cgpa": "average_cgpa", "attendance_percent": "average_attendance",
            "readiness_score": "readiness_score",
            "skill_count": "skill_count", "project_count": "project_count",
            "certification_count": "certification_count",
        }.get(field, field), placed)
        unplaced_value, unplaced_n = _metric_value({
            "cgpa": "average_cgpa", "attendance_percent": "average_attendance",
            "readiness_score": "readiness_score",
            "skill_count": "skill_count", "project_count": "project_count",
            "certification_count": "certification_count",
        }.get(field, field), unplaced)
        # Counts are not predefined metrics; calculate their means directly.
        if field.endswith("_count"):
            p_values = [float(row[field]) for row in placed if row.get(field) is not None]
            u_values = [float(row[field]) for row in unplaced if row.get(field) is not None]
            placed_value = round(sum(p_values) / len(p_values), 2) if p_values else None
            unplaced_value = round(sum(u_values) / len(u_values), 2) if u_values else None
            placed_n, unplaced_n = len(p_values), len(u_values)
        comparison.append({
            "field": field,
            "placed_average": placed_value,
            "unplaced_average": unplaced_value,
            "placed_sample": placed_n,
            "unplaced_sample": unplaced_n,
        })
    obs = observation(
        kind="placement_success_association", entity="student",
        facts={"comparison": comparison, "placed": len(placed), "unplaced": len(unplaced)},
        source="Edvatiq historical placement records", sample_size=len(rows), population_size=total,
        definitions={
            "interpretation": "historical group associations only; no causal or employment-probability claim",
            "placed": "placed, selected, offered, or joined in authorized structured records",
        },
        authorized_scope=envelope.scope_label(total),
    )
    strongest = next((item for item in comparison if item["placed_average"] is not None and item["unplaced_average"] is not None), None)
    answer = (
        f"Across {envelope.scope_label(total)}, the clearest available descriptive difference is in {strongest['field'].replace('_', ' ')}: "
        f"{strongest['placed_average']:g} for placed students versus {strongest['unplaced_average']:g} for unplaced students. "
        "These are historical associations, not causes or predictions."
        if strongest else
        "The authorized data does not contain enough shared evidence fields to compare placed and unplaced students reliably."
    )
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS if strongest else AssistantOutcome.INSUFFICIENT_EVIDENCE,
        answer=answer,
        artifacts=[Artifact(
            id=identifier("artifact"), type="comparison", title="Placed and unplaced profiles",
            data={"metrics": comparison, "placed": len(placed), "unplaced": len(unplaced)},
            evidence_ids=[obs.id],
            security=security(
                permissions=("college.placements.view",), domains=("placements", *sorted(domains - {"placements"})),
                entity_ids=(row["id"] for row in rows), scope={"population": total},
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _analysis_scope(
    envelope: AccessEnvelope,
    current_scope: set[str] | None,
    *,
    permissions: set[str],
    domains: set[str],
) -> set[str] | None:
    missing = permissions - envelope.permissions
    if missing:
        raise AccessViolation(
            AssistantOutcome.ACCESS_LIMITED,
            "This analysis needs additional authorized work areas.",
            missing=missing,
        )
    required_scope = envelope.student_scope(domains)
    if current_scope is None:
        return required_scope
    if required_scope is None:
        return current_scope
    return current_scope & required_scope


def execute_college_query(
    db: Session,
    user: User,
    query: SemanticQuery,
    catalog: SemanticCatalog,
    envelope: AccessEnvelope,
    definitions: dict,
    *,
    offset: int = 0,
    background: bool = False,
) -> AssistantResponse:
    """Execute one validated College semantic query in the current DB session."""
    envelope.require_query(catalog, query)
    fields, unavailable = envelope.projectable_fields(catalog, query)

    if query.entity == "company":
        scope_ids = envelope.student_scope({"placements"})
        return _company_response(
            db, query, envelope, scope_ids, background=background,
        )
    if query.entity == "subject":
        attendance = "attendance_percent" in query.fields or "subject_attendance" in query.metrics
        scope_ids = envelope.student_scope({"attendance"} if attendance else {"assessments"})
        if query.goal == QueryGoal.TREND:
            if attendance:
                return AssistantResponse(
                    outcome=AssistantOutcome.UNSUPPORTED,
                    answer="Subject attendance trends need an explicit comparable-period definition.",
                    scope=envelope.public_scope(),
                )
            return _subject_trend_response(
                db, query, envelope, scope_ids, background=background,
            )
        if attendance:
            return _subject_attendance_response(db, query, envelope, scope_ids)
        return _subject_response(db, query, envelope, definitions, scope_ids)
    if query.entity in {"department", "cohort"}:
        # Structure comparisons use the student population as their denominator.
        translated = SemanticQuery(
            goal=QueryGoal.AGGREGATE,
            entity="student",
            fields=["id", "name", "department", "cohort"],
            metrics=["student_count"],
            group_by=[query.entity],
            limit=query.limit,
        )
        envelope.require_query(catalog, translated)
        translated_fields, _ = envelope.projectable_fields(catalog, translated)
        scope_ids = envelope.student_scope(set())
        return _student_aggregate_response(
            db, translated, translated_fields, envelope, definitions, scope_ids,
            background=background,
        )
    if query.entity != "student":
        return AssistantResponse(
            outcome=AssistantOutcome.UNSUPPORTED,
            answer="That College entity is not registered in the assistant catalog.",
            scope=envelope.public_scope(),
        )

    domains = _required_domains(catalog, query, fields)
    resolution = _resolve_students(db, user, query, envelope, domains)
    if resolution.clarification:
        return resolution.clarification
    has_student_reference = any(item.kind in {"student", "client"} for item in query.entities)
    if has_student_reference and not resolution.ids:
        return AssistantResponse(
            outcome=AssistantOutcome.NOT_FOUND,
            answer="I couldn't find that student in your authorized scope.",
            scope=envelope.public_scope(),
        )
    scope_ids = envelope.student_scope(domains)
    if resolution.ids:
        selected = set(resolution.ids)
        scope_ids = selected if scope_ids is None else scope_ids & selected

    if query.goal == QueryGoal.PROFILE:
        if not resolution.ids:
            return AssistantResponse(
                outcome=AssistantOutcome.CLARIFICATION,
                answer="Which student should I use? Open a student profile or name the student.",
                artifacts=[Artifact(
                    id=identifier("artifact"), type="clarification", title="Student required",
                    data={"reason": "missing_referent"},
                    security=security(permissions=("college.students.view",), domains=("students",)),
                )], scope=envelope.public_scope(),
            )
        return _student_profile(
            db, query, resolution.ids[0], fields, unavailable,
            envelope, definitions,
        )
    if query.goal in {QueryGoal.ELIGIBILITY, QueryGoal.MATCH}:
        return _student_eligibility_response(
            db, query, envelope, scope_ids, background=background,
        )
    if query.requested_analysis in {"offers_pending_joining", "multiple_offer_details"}:
        scope_ids = _analysis_scope(
            envelope, scope_ids,
            permissions={"college.placements.view"}, domains={"placements"},
        )
        return _student_offer_response(
            db, query, envelope, scope_ids, background=background,
        )
    if query.requested_analysis == "drive_attendance_not_recorded":
        return AssistantResponse(
            outcome=AssistantOutcome.INSUFFICIENT_EVIDENCE,
            answer=(
                "Placement applications and outcomes are recorded, but drive attendance is not a governed structured field. "
                "I won't treat an application as proof that a student attended."
            ),
            scope=envelope.public_scope(),
        )
    if query.requested_analysis == "company_group_selection_rate":
        scope_ids = _analysis_scope(
            envelope, scope_ids,
            permissions={"college.placements.view"}, domains={"placements"},
        )
        return _company_group_selection_response(
            db, query, envelope, scope_ids,
        )
    if any(item.field in {"subject", "subject_score"} for item in query.filters):
        return _subject_students_response(db, query, envelope, definitions, scope_ids)
    if query.goal == QueryGoal.COMPARE and resolution.ids:
        return _student_comparison_response(
            db, query, fields, unavailable, envelope, definitions, scope_ids,
        )
    if query.goal == QueryGoal.CORRELATION:
        scope_ids = _analysis_scope(
            envelope, scope_ids,
            permissions={"college.assessments.view", "college.attendance.view"},
            domains={"assessments", "attendance"},
        )
        return _correlation_response(
            db, query, envelope, definitions, scope_ids, background=background,
        )
    if query.goal == QueryGoal.TREND:
        analysis = query.requested_analysis or "academic_change"
        if analysis in {
            "consistent_core_subject_weakness", "difficult_subject_improvement",
        }:
            scope_ids = _analysis_scope(
                envelope, scope_ids,
                permissions={"college.assessments.view"}, domains={"assessments"},
            )
            return _student_subject_trend_response(
                db, query, envelope, definitions, scope_ids, background=background,
            )
        if analysis in {"attendance_change", "attendance_drop", "consistent_attendance"}:
            permissions = {"college.attendance.view"}
            analysis_domains = {"attendance"}
        elif analysis == "readiness_change":
            permissions = {"college.readiness.view"}
            analysis_domains = {"readiness"}
        else:
            permissions = {"college.assessments.view"}
            analysis_domains = {"assessments"}
        scope_ids = _analysis_scope(
            envelope, scope_ids,
            permissions=permissions, domains=analysis_domains,
        )
        return _trend_response(
            db, query, envelope, definitions, scope_ids, background=background,
        )
    if query.goal == QueryGoal.ANALYZE:
        scope_ids = _analysis_scope(
            envelope, scope_ids,
            permissions={"college.placements.view"}, domains={"placements"},
        )
        if query.requested_analysis == "placed_skill_frequency":
            scope_ids = _analysis_scope(
                envelope, scope_ids,
                permissions={"college.placements.view", "college.readiness.view"},
                domains={"placements", "readiness"},
            )
            return _placement_skill_frequency_response(
                db, query, envelope, scope_ids, background=background,
            )
        if query.requested_analysis == "rejection_reasons_not_structured":
            return AssistantResponse(
                outcome=AssistantOutcome.INSUFFICIENT_EVIDENCE,
                answer=(
                    "Rejection outcomes are structured, but rejection reasons are not recorded as a reviewed categorical field. "
                    "I won't infer reasons from free-text notes or stage history."
                ),
                scope=envelope.public_scope(),
            )
        if query.requested_analysis == "high_package_definition_required":
            return AssistantResponse(
                outcome=AssistantOutcome.CLARIFICATION,
                answer="What package threshold should count as high-paying, for example INR 10 LPA?",
                scope=envelope.public_scope(),
            )
        if query.requested_analysis == "unselected_missing_required_skills":
            return AssistantResponse(
                outcome=AssistantOutcome.INSUFFICIENT_EVIDENCE,
                answer=(
                    "I can compare verified skills with structured company requirements, but missing skills alone cannot be "
                    "reported as rejection reasons. Name a company or drive to run an evidence-gap comparison."
                ),
                scope=envelope.public_scope(),
            )
        if query.requested_analysis not in {None, "placement_success_associations"}:
            return AssistantResponse(
                outcome=AssistantOutcome.UNSUPPORTED,
                answer="That descriptive analysis does not yet have a governed College definition.",
                scope=envelope.public_scope(),
            )
        return _placement_analysis_response(
            db, query, envelope, definitions, scope_ids, background=background,
        )
    if query.goal in {QueryGoal.AGGREGATE, QueryGoal.COMPARE} and query.metrics:
        return _student_aggregate_response(
            db, query, fields, envelope, definitions, scope_ids,
            background=background,
        )
    return _student_records_response(
        db, query, fields, unavailable, envelope, definitions, scope_ids,
        offset=offset,
    )


def _resolve_students(
    db: Session, user: User, query: SemanticQuery, envelope: AccessEnvelope,
    domains: set[str],
) -> StudentResolution:
    ids, labels = [], {}
    for ref in query.entities:
        if ref.kind not in {"student", "client"}:
            continue
        selected = None
        if ref.id:
            selected = validate_entity_ref(db, user, "student", ref.id)
        elif ref.label:
            result = resolve_entities(db, user, ref.label, ["student"], 8, include_media=False)
            if result.get("resolution") == "ambiguous":
                return StudentResolution([], {}, _clarification_response(query, result.get("items", []), envelope))
            selected = result.get("selected")
        if not selected:
            return StudentResolution([], {})
        student_id = selected["id"]
        if not envelope.allows_student(student_id, domains):
            # Named entities outside scope are deliberately indistinguishable
            # from records that do not exist.
            return StudentResolution([], {})
        ids.append(student_id)
        labels[student_id] = selected.get("display_name") or ref.label or "Student"
    return StudentResolution(list(dict.fromkeys(ids)), labels)


def _identity_row(db: Session, organization_id: str, student_id: str):
    return db.execute(
        select(CollegeStudentProfile, Client, CollegeProgram, CollegeDepartment, CollegeCohort)
        .join(Client, Client.id == CollegeStudentProfile.client_id)
        .join(CollegeProgram, CollegeProgram.id == CollegeStudentProfile.program_id)
        .join(CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id)
        .join(CollegeCohort, CollegeCohort.id == CollegeStudentProfile.cohort_id)
        .where(
            CollegeStudentProfile.organization_id == organization_id,
            CollegeStudentProfile.id == student_id,
        )
    ).first()


def _readiness_policy(db: Session, organization_id: str) -> CollegeReadinessPolicy | None:
    return db.execute(select(CollegeReadinessPolicy).where(
        CollegeReadinessPolicy.organization_id == organization_id,
        CollegeReadinessPolicy.is_active.is_(True),
    ).order_by(CollegeReadinessPolicy.version.desc())).scalars().first()


def _student_profile(
    db: Session,
    query: SemanticQuery,
    student_id: str,
    fields: list[str],
    unavailable: list[str],
    envelope: AccessEnvelope,
    definitions: dict,
) -> AssistantResponse:
    pair = _identity_row(db, envelope.organization_id, student_id)
    if not pair:
        return AssistantResponse(
            outcome=AssistantOutcome.NOT_FOUND,
            answer="I couldn't find that student in your authorized scope.",
            scope=envelope.public_scope(),
        )
    student, client, program, department, cohort = pair
    requested = set(fields)
    facts: dict[str, Any] = {
        "name": f"{client.first_name} {client.last_name}".strip(),
        "admission_number": student.admission_number,
        "roll_number": student.roll_number,
        "status": student.status,
        "semester": student.current_semester,
        "program": {"code": program.code, "name": program.name},
        "department": {"code": department.code, "name": department.name},
        "cohort": {
            "code": cohort.code, "name": cohort.name,
            "section": cohort.section, "graduation_year": cohort.graduation_year,
        },
        "section": cohort.section,
        "graduation_year": cohort.graduation_year,
    }
    if "email" in requested:
        facts["email"] = client.email
    if "phone" in requested:
        facts["phone"] = client.phone

    source_timestamps = [student.updated_at, client.updated_at]
    if requested & ACADEMIC_FIELDS:
        terms = list(db.execute(select(CollegeTermResult).where(
            CollegeTermResult.organization_id == envelope.organization_id,
            CollegeTermResult.student_profile_id == student_id,
            CollegeTermResult.result_status == "published",
        ).order_by(
            CollegeTermResult.semester.desc(),
            CollegeTermResult.published_on.desc().nullslast(),
            CollegeTermResult.created_at.desc(),
        )).scalars())
        latest = terms[0] if terms else None
        facts.update({
            "cgpa": float(latest.cgpa) if latest and latest.cgpa is not None else None,
            "sgpa": float(latest.sgpa) if latest and latest.sgpa is not None else None,
            "active_backlogs": latest.active_backlogs if latest else None,
            "academic_history": [{
                "semester": row.semester,
                "sgpa": float(row.sgpa) if row.sgpa is not None else None,
                "cgpa": float(row.cgpa) if row.cgpa is not None else None,
                "active_backlogs": row.active_backlogs,
                "published_on": row.published_on.isoformat() if row.published_on else None,
            } for row in terms],
        })
        source_timestamps.extend(row.updated_at for row in terms)

    if requested & ATTENDANCE_FIELDS:
        attendance = list(db.execute(select(CollegeAttendanceSnapshot).where(
            CollegeAttendanceSnapshot.organization_id == envelope.organization_id,
            CollegeAttendanceSnapshot.student_profile_id == student_id,
            CollegeAttendanceSnapshot.course_id.is_(None),
        ).order_by(CollegeAttendanceSnapshot.as_of.desc(), CollegeAttendanceSnapshot.created_at.desc())).scalars())
        latest = attendance[0] if attendance else None
        facts["attendance_percent"] = float(latest.attendance_percent) if latest and latest.attendance_percent is not None else None
        facts["attendance_history"] = [{
            "attendance_percent": float(row.attendance_percent) if row.attendance_percent is not None else None,
            "classes_held": row.classes_held, "classes_attended": row.classes_attended,
            "as_of": row.as_of.isoformat(),
        } for row in attendance]
        source_timestamps.extend(row.updated_at for row in attendance)

    if requested & READINESS_FIELDS:
        policy = _readiness_policy(db, envelope.organization_id)
        snapshot_statement = select(CollegeReadinessSnapshot).where(
            CollegeReadinessSnapshot.organization_id == envelope.organization_id,
            CollegeReadinessSnapshot.student_profile_id == student_id,
        )
        if policy:
            snapshot_statement = snapshot_statement.where(
                CollegeReadinessSnapshot.policy_id == policy.id,
            )
        snapshot = db.execute(snapshot_statement.order_by(
            CollegeReadinessSnapshot.calculated_at.desc(),
        )).scalars().first() if policy else None
        minimum = float(policy.minimum_coverage_percent) if policy else 60.0
        rankable = bool(snapshot and snapshot.score is not None and float(snapshot.coverage_percent) >= minimum)
        facts.update({
            "readiness_score": float(snapshot.score) if rankable else None,
            "readiness_band": snapshot.band if rankable else "insufficient_evidence",
            "readiness_coverage": float(snapshot.coverage_percent) if snapshot else 0.0,
            "readiness_missing_evidence": list(snapshot.missing_evidence or []) if snapshot else [],
            "readiness_policy_version": snapshot.policy_version if snapshot else (policy.version if policy else None),
        })
        if snapshot:
            source_timestamps.append(snapshot.updated_at)

        if requested & {"skills", "projects", "certifications", "skill_count", "project_count", "certification_count", "internship_count", "profile_complete"}:
            evidence = list(db.execute(select(CollegeCareerEvidence).where(
                CollegeCareerEvidence.organization_id == envelope.organization_id,
                CollegeCareerEvidence.student_profile_id == student_id,
                CollegeCareerEvidence.is_verified.is_(True),
            ).order_by(CollegeCareerEvidence.evidence_type, CollegeCareerEvidence.completed_on.desc().nullslast())).scalars())
            for key, kind in (("skills", "skill"), ("projects", "project"), ("certifications", "certification")):
                facts[key] = [{
                    "id": row.id, "title": row.title, "issuer": row.issuer,
                    "verified": row.is_verified, "proficiency": row.proficiency,
                    "completed_on": row.completed_on.isoformat() if row.completed_on else None,
                } for row in evidence if row.evidence_type == kind]
                facts[f"{key[:-1]}_count" if key.endswith("s") else f"{key}_count"] = len(facts[key])
            facts["skill_count"] = len(facts.get("skills", []))
            facts["project_count"] = len(facts.get("projects", []))
            facts["certification_count"] = len(facts.get("certifications", []))
            facts["internship_count"] = sum(row.evidence_type == "internship" for row in evidence)
            source_timestamps.extend(row.updated_at for row in evidence)

            career = db.execute(select(CollegeCareerProfile).where(
                CollegeCareerProfile.organization_id == envelope.organization_id,
                CollegeCareerProfile.student_profile_id == student_id,
            )).scalar_one_or_none()
            facts["profile_complete"] = bool(
                career and career.resume_status not in {None, "missing"}
                and facts["skill_count"] > 0 and facts["project_count"] > 0
            )

        if "training_count" in requested:
            facts["training_count"] = int(db.scalar(select(func.count(CollegePreparationActivity.id)).where(
                CollegePreparationActivity.organization_id == envelope.organization_id,
                CollegePreparationActivity.student_profile_id == student_id,
                CollegePreparationActivity.status == "completed",
            )) or 0)

    if requested & CODING_FIELDS:
        coding = db.execute(select(CollegeCodingSnapshot).where(
            CollegeCodingSnapshot.organization_id == envelope.organization_id,
            CollegeCodingSnapshot.student_profile_id == student_id,
        ).order_by(CollegeCodingSnapshot.captured_at.desc())).scalars().first()
        facts["coding_total"] = coding.total_solved if coding else None
        facts["coding_languages"] = list(coding.languages or []) if coding else []
        if coding:
            source_timestamps.append(coding.updated_at)

    if requested & PLACEMENT_FIELDS:
        career = db.execute(select(CollegeCareerProfile).where(
            CollegeCareerProfile.organization_id == envelope.organization_id,
            CollegeCareerProfile.student_profile_id == student_id,
        )).scalar_one_or_none()
        applications = list(db.execute(select(CollegePlacementApplication).where(
            CollegePlacementApplication.organization_id == envelope.organization_id,
            CollegePlacementApplication.student_profile_id == student_id,
        )).scalars())
        application_ids = [row.id for row in applications]
        offers = list(db.execute(select(CollegePlacementOffer).where(
            CollegePlacementOffer.organization_id == envelope.organization_id,
            CollegePlacementOffer.application_id.in_(application_ids),
        )).scalars()) if application_ids else []
        placed = bool(
            career and career.placement_status in {"placed", "joined"}
            or any(row.outcome in {"selected", "offered", "joined"} for row in applications)
        )
        facts.update({
            "placement_status": "placed" if placed else "unplaced",
            "eligible_company_count": sum(
                (row.eligibility_override_status or row.eligibility_status) == "eligible"
                for row in applications
            ),
            "offer_count": len(offers),
            "highest_package": max((row.package_paise or 0 for row in offers), default=None),
            "offers": [{
                "id": row.id, "status": row.status, "role": row.offered_role,
                "package_paise": row.package_paise,
            } for row in offers],
        })
        source_timestamps.extend(row.updated_at for row in applications)
        source_timestamps.extend(row.updated_at for row in offers)

    visible = {key: json_value(value) for key, value in facts.items() if key in requested or key in {
        "name", "program", "department", "cohort",
        "readiness_missing_evidence", "readiness_policy_version",
    }}
    visible["profile_ref"] = {"kind": "client", "id": client.id}
    obs = observation(
        kind="student_profile", entity="student", facts=visible,
        source="Edvatiq College records",
        source_timestamp=max((item for item in source_timestamps if item), default=None),
        sample_size=1, population_size=1,
        coverage_percent=facts.get("readiness_coverage"),
        definitions=_definitions_for_fields(requested, definitions),
        authorized_scope=envelope.scope_label(1),
    )

    answer = (
        f"{facts['name']} is currently marked {student.status} and studies "
        f"{program.name} in {cohort.name}."
    )
    academic_highlights = []
    if facts.get("cgpa") is not None:
        academic_highlights.append(f"a current CGPA of {facts['cgpa']:.2f}")
    if facts.get("attendance_percent") is not None:
        academic_highlights.append(f"{facts['attendance_percent']:.1f}% attendance")
    if academic_highlights:
        answer += f" The available academic record shows {' and '.join(academic_highlights)}."
    placement_highlights = []
    if facts.get("readiness_score") is not None:
        placement_highlights.append(
            f"a placement-readiness score of {facts['readiness_score']:.1f} "
            f"({facts['readiness_band'].replace('_', ' ')})"
        )
    if facts.get("placement_status"):
        placement_highlights.append(f"a current status of {facts['placement_status']}")
    if placement_highlights:
        answer += f" For placements, the record shows {' and '.join(placement_highlights)}."
    if unavailable:
        answer += " I've omitted fields outside your current work areas or sensitive-field access."

    profile_security = security(
        permissions=(
            "college.students.view",
            *(["college.students.contact.view"] if requested & {"email", "phone"} else []),
        ),
        domains=("students", *sorted(
            (ACADEMIC_FIELDS & requested and {"assessments"} or set())
            | (ATTENDANCE_FIELDS & requested and {"attendance"} or set())
            | (READINESS_FIELDS & requested and {"readiness"} or set())
            | (CODING_FIELDS & requested and {"coding"} or set())
            | (PLACEMENT_FIELDS & requested and {"placements"} or set())
        )),
        entity_ids=(student_id,),
        entity_refs=({"kind": "student", "id": student_id, "label": facts["name"]},),
    )
    artifacts = [Artifact(
        id=identifier("artifact"), type="profile", title=facts["name"],
        data=visible, evidence_ids=[obs.id],
        security=profile_security,
    )]
    if unavailable:
        artifacts.append(Artifact(
            id=identifier("artifact"), type="notice", title="Access-limited fields",
            data={"unavailable_fields": unavailable},
            security=security(permissions=("ai.use",)),
        ))
    suggestions = [
        Suggestion(
            id=identifier("suggestion"), label="Academic history",
            prompt="Show this student's semester-wise academic performance",
            entity_refs=[EntityRef(kind="student", id=student_id, label=facts["name"])],
            security=security(
                permissions=("college.students.view", "college.assessments.view"),
                domains=("students", "assessments"), entity_ids=(student_id,),
                entity_refs=({"kind": "student", "id": student_id, "label": facts["name"]},),
            ),
        ),
        Suggestion(
            id=identifier("suggestion"), label="Placement readiness",
            prompt="Explain this student's placement readiness",
            entity_refs=[EntityRef(kind="student", id=student_id, label=facts["name"])],
            security=security(
                permissions=("college.students.view", "college.readiness.view"),
                domains=("students", "readiness"), entity_ids=(student_id,),
                entity_refs=({"kind": "student", "id": student_id, "label": facts["name"]},),
            ),
        ),
    ]
    return AssistantResponse(
        outcome=AssistantOutcome.PARTIAL if unavailable else AssistantOutcome.SUCCESS,
        answer=answer, artifacts=artifacts, suggestions=suggestions,
        observations=[obs], scope=envelope.public_scope(),
    )


def _ranked_subquery(model, organization_id: str, order_by, *columns, predicates=()):
    return select(
        *columns,
        func.row_number().over(
            partition_by=model.student_profile_id,
            order_by=order_by,
        ).label("position"),
    ).where(model.organization_id == organization_id, *predicates).subquery()


def _apply_filter(statement, expression, operator: FilterOperator, value):
    if operator == FilterOperator.EQ:
        return statement.where(expression == value)
    if operator == FilterOperator.NE:
        return statement.where(expression != value)
    if operator == FilterOperator.GT:
        return statement.where(expression > value)
    if operator == FilterOperator.GTE:
        return statement.where(expression >= value)
    if operator == FilterOperator.LT:
        return statement.where(expression < value)
    if operator == FilterOperator.LTE:
        return statement.where(expression <= value)
    if operator == FilterOperator.IN:
        values = value if isinstance(value, list) else [value]
        return statement.where(expression.in_(values))
    if operator == FilterOperator.NOT_IN:
        values = value if isinstance(value, list) else [value]
        return statement.where(expression.notin_(values))
    if operator == FilterOperator.CONTAINS:
        return statement.where(func.lower(func.coalesce(expression, "")).contains(str(value).casefold()))
    if operator == FilterOperator.IS_NULL:
        return statement.where(expression.is_(None) if value is not False else expression.is_not(None))
    raise ValueError(f"Unsupported filter operator: {operator}")


def _student_dataset(
    db: Session,
    query: SemanticQuery,
    fields: set[str],
    envelope: AccessEnvelope,
    scope_ids: set[str] | None,
    *,
    limit: int | None = None,
    offset: int = 0,
    hard_limit: int = 5000,
) -> tuple[list[dict], int, CollegeReadinessPolicy | None]:
    organization_id = envelope.organization_id
    needed = set(fields) | {item.field for item in query.filters} | {item.field for item in query.sort}
    for metric in query.metrics:
        needed.update({
            "student_count": set(),
            "average_cgpa": {"cgpa"},
            "average_attendance": {"attendance_percent"},
                "placement_rate": {"placement_status"},
                "average_package": {"highest_package"},
                "readiness_score": {"readiness_score", "readiness_coverage"},
                "average_skill_count": {"skill_count"},
                "certification_total": {"certification_count"},
                "internship_participation_rate": {"internship_count"},
            }.get(metric, set()))

    name = func.trim(Client.first_name + literal(" ") + Client.last_name)
    columns = [
        CollegeStudentProfile.id.label("id"),
        name.label("name"),
        CollegeStudentProfile.admission_number.label("admission_number"),
        CollegeStudentProfile.roll_number.label("roll_number"),
        CollegeStudentProfile.status.label("status"),
        CollegeStudentProfile.current_semester.label("semester"),
        CollegeStudentProfile.program_id.label("_program_id"),
        CollegeStudentProfile.cohort_id.label("_cohort_id"),
        CollegeProgram.name.label("program"),
        CollegeProgram.code.label("program_code"),
        CollegeDepartment.name.label("department"),
        CollegeDepartment.id.label("_department_id"),
        CollegeDepartment.code.label("department_code"),
        CollegeCohort.name.label("cohort"),
        CollegeCohort.code.label("cohort_code"),
        CollegeCohort.section.label("section"),
        CollegeCohort.graduation_year.label("graduation_year"),
        CollegeStudentProfile.updated_at.label("source_updated_at"),
    ]
    statement = (
        select(*columns)
        .select_from(CollegeStudentProfile)
        .join(Client, Client.id == CollegeStudentProfile.client_id)
        .join(CollegeProgram, CollegeProgram.id == CollegeStudentProfile.program_id)
        .join(CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id)
        .join(CollegeCohort, CollegeCohort.id == CollegeStudentProfile.cohort_id)
        .where(
            CollegeStudentProfile.organization_id == organization_id,
            CollegeStudentProfile.status == "active",
        )
    )
    expressions: dict[str, Any] = {
        "id": CollegeStudentProfile.id,
        "name": name,
        "admission_number": CollegeStudentProfile.admission_number,
        "roll_number": CollegeStudentProfile.roll_number,
        "status": CollegeStudentProfile.status,
        "semester": CollegeStudentProfile.current_semester,
        "program": CollegeProgram.name,
        "program_id": CollegeProgram.id,
        "department": CollegeDepartment.name,
        "department_id": CollegeDepartment.id,
        "cohort": CollegeCohort.name,
        "cohort_id": CollegeCohort.id,
        "section": CollegeCohort.section,
        "graduation_year": CollegeCohort.graduation_year,
    }
    if scope_ids is not None:
        statement = statement.where(CollegeStudentProfile.id.in_(scope_ids))

    if needed & ACADEMIC_FIELDS:
        latest_term = _ranked_subquery(
            CollegeTermResult,
            organization_id,
            (
                CollegeTermResult.semester.desc(),
                CollegeTermResult.published_on.desc().nullslast(),
                CollegeTermResult.created_at.desc(),
            ),
            CollegeTermResult.student_profile_id.label("student_id"),
            CollegeTermResult.cgpa.label("cgpa"),
            CollegeTermResult.sgpa.label("sgpa"),
            CollegeTermResult.active_backlogs.label("active_backlogs"),
            predicates=(CollegeTermResult.result_status == "published",),
        )
        statement = statement.outerjoin(latest_term, and_(
            latest_term.c.student_id == CollegeStudentProfile.id,
            latest_term.c.position == 1,
        )).add_columns(
            latest_term.c.cgpa,
            latest_term.c.sgpa,
            latest_term.c.active_backlogs,
        )
        expressions.update({
            "cgpa": latest_term.c.cgpa,
            "sgpa": latest_term.c.sgpa,
            "active_backlogs": latest_term.c.active_backlogs,
        })

    if needed & ATTENDANCE_FIELDS:
        attendance_source = select(
            CollegeAttendanceSnapshot.student_profile_id.label("student_id"),
            CollegeAttendanceSnapshot.attendance_percent.label("attendance_percent"),
            func.row_number().over(
                partition_by=CollegeAttendanceSnapshot.student_profile_id,
                order_by=(
                    CollegeAttendanceSnapshot.as_of.desc(),
                    CollegeAttendanceSnapshot.created_at.desc(),
                ),
            ).label("position"),
        ).where(
            CollegeAttendanceSnapshot.organization_id == organization_id,
            CollegeAttendanceSnapshot.course_id.is_(None),
        ).subquery()
        statement = statement.outerjoin(attendance_source, and_(
            attendance_source.c.student_id == CollegeStudentProfile.id,
            attendance_source.c.position == 1,
        )).add_columns(attendance_source.c.attendance_percent)
        expressions["attendance_percent"] = attendance_source.c.attendance_percent

    policy = None
    if needed & READINESS_FIELDS:
        policy = _readiness_policy(db, organization_id)
        latest_readiness = _ranked_subquery(
            CollegeReadinessSnapshot,
            organization_id,
            CollegeReadinessSnapshot.calculated_at.desc(),
            CollegeReadinessSnapshot.student_profile_id.label("student_id"),
            CollegeReadinessSnapshot.score.label("raw_readiness_score"),
            CollegeReadinessSnapshot.band.label("raw_readiness_band"),
            CollegeReadinessSnapshot.coverage_percent.label("readiness_coverage"),
            predicates=(CollegeReadinessSnapshot.policy_id == policy.id,) if policy else (),
        )
        minimum = policy.minimum_coverage_percent if policy else Decimal("100.01")
        readiness_score = case(
            (latest_readiness.c.readiness_coverage >= minimum, latest_readiness.c.raw_readiness_score),
            else_=None,
        )
        readiness_band = case(
            (latest_readiness.c.readiness_coverage >= minimum, latest_readiness.c.raw_readiness_band),
            else_="insufficient_evidence",
        )
        statement = statement.outerjoin(latest_readiness, and_(
            latest_readiness.c.student_id == CollegeStudentProfile.id,
            latest_readiness.c.position == 1,
        )).add_columns(
            readiness_score.label("readiness_score"),
            readiness_band.label("readiness_band"),
            latest_readiness.c.readiness_coverage,
        )
        expressions.update({
            "readiness_score": readiness_score,
            "readiness_band": readiness_band,
            "readiness_coverage": latest_readiness.c.readiness_coverage,
        })

        if needed & {
            "skill_count", "project_count", "certification_count", "internship_count",
            "skills", "projects", "certifications", "profile_complete",
        }:
            evidence_counts = select(
                CollegeCareerEvidence.student_profile_id.label("student_id"),
                func.sum(case((CollegeCareerEvidence.evidence_type == "skill", 1), else_=0)).label("skill_count"),
                func.sum(case((CollegeCareerEvidence.evidence_type == "project", 1), else_=0)).label("project_count"),
                func.sum(case((CollegeCareerEvidence.evidence_type == "certification", 1), else_=0)).label("certification_count"),
                func.sum(case((CollegeCareerEvidence.evidence_type == "internship", 1), else_=0)).label("internship_count"),
            ).where(
                CollegeCareerEvidence.organization_id == organization_id,
                CollegeCareerEvidence.is_verified.is_(True),
            ).group_by(CollegeCareerEvidence.student_profile_id).subquery()
            statement = statement.outerjoin(
                evidence_counts, evidence_counts.c.student_id == CollegeStudentProfile.id,
            ).add_columns(
                func.coalesce(evidence_counts.c.skill_count, 0).label("skill_count"),
                func.coalesce(evidence_counts.c.project_count, 0).label("project_count"),
                func.coalesce(evidence_counts.c.certification_count, 0).label("certification_count"),
                func.coalesce(evidence_counts.c.internship_count, 0).label("internship_count"),
            )
            expressions.update({
                "skill_count": func.coalesce(evidence_counts.c.skill_count, 0),
                "project_count": func.coalesce(evidence_counts.c.project_count, 0),
                "certification_count": func.coalesce(evidence_counts.c.certification_count, 0),
                "internship_count": func.coalesce(evidence_counts.c.internship_count, 0),
            })

        if "training_count" in needed:
            training = select(
                CollegePreparationActivity.student_profile_id.label("student_id"),
                func.count(CollegePreparationActivity.id).label("training_count"),
            ).where(
                CollegePreparationActivity.organization_id == organization_id,
                CollegePreparationActivity.status == "completed",
            ).group_by(CollegePreparationActivity.student_profile_id).subquery()
            statement = statement.outerjoin(
                training, training.c.student_id == CollegeStudentProfile.id,
            ).add_columns(func.coalesce(training.c.training_count, 0).label("training_count"))
            expressions["training_count"] = func.coalesce(training.c.training_count, 0)

        if "profile_complete" in needed:
            statement = statement.outerjoin(
                CollegeCareerProfile,
                CollegeCareerProfile.student_profile_id == CollegeStudentProfile.id,
            )
            complete = and_(
                CollegeCareerProfile.id.is_not(None),
                CollegeCareerProfile.resume_status.notin_(("missing", "")),
                expressions.get("skill_count", literal(0)) > 0,
                expressions.get("project_count", literal(0)) > 0,
            )
            statement = statement.add_columns(complete.label("profile_complete"))
            expressions["profile_complete"] = complete

    if needed & CODING_FIELDS:
        latest_coding = _ranked_subquery(
            CollegeCodingSnapshot,
            organization_id,
            CollegeCodingSnapshot.captured_at.desc(),
            CollegeCodingSnapshot.student_profile_id.label("student_id"),
            CollegeCodingSnapshot.total_solved.label("coding_total"),
            CollegeCodingSnapshot.languages.label("coding_languages"),
        )
        statement = statement.outerjoin(latest_coding, and_(
            latest_coding.c.student_id == CollegeStudentProfile.id,
            latest_coding.c.position == 1,
        )).add_columns(latest_coding.c.coding_total, latest_coding.c.coding_languages)
        expressions.update({
            "coding_total": latest_coding.c.coding_total,
            "coding_languages": latest_coding.c.coding_languages,
        })

    if needed & PLACEMENT_FIELDS:
        career_alias_needed = "profile_complete" not in needed
        if career_alias_needed:
            statement = statement.outerjoin(
                CollegeCareerProfile,
                CollegeCareerProfile.student_profile_id == CollegeStudentProfile.id,
            )
        application_stats = select(
            CollegePlacementApplication.student_profile_id.label("student_id"),
            func.sum(case((
                or_(
                    CollegePlacementApplication.eligibility_override_status == "eligible",
                    and_(
                        CollegePlacementApplication.eligibility_override_status.is_(None),
                        CollegePlacementApplication.eligibility_status == "eligible",
                    ),
                ), 1,
            ), else_=0)).label("eligible_company_count"),
            func.max(case((
                CollegePlacementApplication.outcome.in_(("selected", "offered", "joined")), 1,
            ), else_=0)).label("has_placement"),
        ).where(
            CollegePlacementApplication.organization_id == organization_id,
        ).group_by(CollegePlacementApplication.student_profile_id).subquery()
        offer_stats = select(
            CollegePlacementApplication.student_profile_id.label("student_id"),
            func.count(CollegePlacementOffer.id).label("offer_count"),
            func.max(CollegePlacementOffer.package_paise).label("highest_package"),
        ).join(
            CollegePlacementOffer,
            CollegePlacementOffer.application_id == CollegePlacementApplication.id,
        ).where(
            CollegePlacementApplication.organization_id == organization_id,
            CollegePlacementOffer.organization_id == organization_id,
        ).group_by(CollegePlacementApplication.student_profile_id).subquery()
        placement_status = case(
            (or_(
                CollegeCareerProfile.placement_status.in_(("placed", "joined")),
                application_stats.c.has_placement == 1,
            ), "placed"),
            else_="unplaced",
        )
        statement = statement.outerjoin(
            application_stats, application_stats.c.student_id == CollegeStudentProfile.id,
        ).outerjoin(
            offer_stats, offer_stats.c.student_id == CollegeStudentProfile.id,
        ).add_columns(
            placement_status.label("placement_status"),
            func.coalesce(application_stats.c.eligible_company_count, 0).label("eligible_company_count"),
            func.coalesce(offer_stats.c.offer_count, 0).label("offer_count"),
            offer_stats.c.highest_package,
        )
        expressions.update({
            "placement_status": placement_status,
            "eligible_company_count": func.coalesce(application_stats.c.eligible_company_count, 0),
            "offer_count": func.coalesce(offer_stats.c.offer_count, 0),
            "highest_package": offer_stats.c.highest_package,
        })

    for item in query.filters:
        if item.field == "skills":
            values = item.value if isinstance(item.value, list) else [item.value]
            for value in values:
                statement = statement.where(exists(select(CollegeCareerEvidence.id).where(
                    CollegeCareerEvidence.organization_id == organization_id,
                    CollegeCareerEvidence.student_profile_id == CollegeStudentProfile.id,
                    CollegeCareerEvidence.evidence_type == "skill",
                    CollegeCareerEvidence.is_verified.is_(True),
                    func.lower(CollegeCareerEvidence.title).contains(str(value).casefold()),
                )))
            continue
        expression = expressions.get(item.field)
        if expression is None:
            continue
        value = item.value
        if item.field in {"department", "program", "cohort"} and item.operator in {
            FilterOperator.EQ, FilterOperator.CONTAINS, FilterOperator.IN,
        }:
            code_expression = {
                "department": CollegeDepartment.code,
                "program": CollegeProgram.code,
                "cohort": CollegeCohort.code,
            }[item.field]
            values = value if isinstance(value, list) else [value]
            statement = statement.where(or_(*[
                or_(
                    func.lower(expression).contains(str(item_value).casefold()),
                    func.lower(code_expression) == str(item_value).casefold(),
                ) for item_value in values
            ]))
            continue
        statement = _apply_filter(statement, expression, item.operator, value)

    if query.qualitative_definition == "overall_good_student" and "readiness_score" in expressions:
        statement = statement.where(expressions["readiness_score"].is_not(None))
    total = int(db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0)
    order = []
    for item in query.sort:
        expression = expressions.get(item.field)
        if expression is not None:
            order.append((expression.desc() if item.direction == "desc" else expression.asc()).nullslast())
    if not order:
        order = [func.lower(name), CollegeStudentProfile.id]
    else:
        order.extend((func.lower(name), CollegeStudentProfile.id))
    statement = statement.order_by(*order)
    if offset:
        statement = statement.offset(max(offset, 0))
    if limit is not None:
        statement = statement.limit(min(max(limit, 1), max(hard_limit, 1)))
    rows = [dict(row._mapping) for row in db.execute(statement).all()]
    requested_evidence = needed & {"skills", "projects", "certifications"}
    if rows and requested_evidence:
        evidence_types = {
            "skills": "skill", "projects": "project", "certifications": "certification",
        }
        grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
        evidence_rows = db.execute(select(CollegeCareerEvidence).where(
            CollegeCareerEvidence.organization_id == organization_id,
            CollegeCareerEvidence.student_profile_id.in_([row["id"] for row in rows]),
            CollegeCareerEvidence.evidence_type.in_([
                evidence_types[key] for key in requested_evidence
            ]),
            CollegeCareerEvidence.is_verified.is_(True),
        ).order_by(
            CollegeCareerEvidence.student_profile_id,
            CollegeCareerEvidence.evidence_type,
            CollegeCareerEvidence.completed_on.desc().nullslast(),
        )).scalars()
        reverse_types = {value: key for key, value in evidence_types.items()}
        for evidence in evidence_rows:
            grouped[evidence.student_profile_id][reverse_types[evidence.evidence_type]].append({
                "id": evidence.id,
                "title": evidence.title,
                "issuer": evidence.issuer,
                "proficiency": evidence.proficiency,
                "completed_on": evidence.completed_on,
            })
        for row in rows:
            for key in requested_evidence:
                row[key] = grouped[row["id"]].get(key, [])
    return [{key: json_value(value) for key, value in row.items()} for row in rows], total, policy


def _student_records_response(
    db: Session,
    query: SemanticQuery,
    fields: list[str],
    unavailable: list[str],
    envelope: AccessEnvelope,
    definitions: dict,
    scope_ids: set[str] | None,
    *,
    offset: int = 0,
) -> AssistantResponse:
    rows, total, policy = _student_dataset(
        db, query, set(fields), envelope, scope_ids, limit=query.limit, offset=offset,
    )
    if query.qualitative_definition == "overall_good_student" and not policy:
        return AssistantResponse(
            outcome=AssistantOutcome.CONFIGURATION_REQUIRED,
            answer="Placement readiness has not been configured yet, so I can't rank an overall good student reliably.",
            artifacts=[Artifact(
                id=identifier("artifact"), type="notice", title="Readiness policy required",
                data={"setting": "placement_readiness"},
                security=security(permissions=("college.readiness.view",), domains=("readiness",)),
            )], scope=envelope.public_scope(),
        )
    if not rows:
        return AssistantResponse(
            outcome=AssistantOutcome.EMPTY,
            answer="I found no matching students in your authorized scope.",
            artifacts=[Artifact(
                id=identifier("artifact"), type="records", title="No matching students",
                data={"items": [], "total": 0, "has_more": False},
                security=security(permissions=("college.students.view",), domains=("students",)),
            )], scope=envelope.public_scope(),
        )

    projected = []
    identity = {"id", "name", "admission_number", "department", "program", "cohort", "section", "graduation_year"}
    for rank, row in enumerate(rows, start=offset + 1):
        item = {key: row.get(key) for key in identity | set(fields) if key in row}
        item["rank"] = rank if query.goal == QueryGoal.RANK else None
        item["profile_ref"] = {"kind": "student", "id": row["id"]}
        projected.append(item)
    source_timestamp = max(
        (row.get("source_updated_at") for row in rows if row.get("source_updated_at")),
        default=None,
    )
    covered = 0
    coverage_field = next((key for key in ("readiness_score", "cgpa", "attendance_percent") if key in fields), None)
    if coverage_field:
        covered = sum(row.get(coverage_field) is not None for row in rows)
    coverage = round(covered * 100 / len(rows), 1) if coverage_field and rows else None
    definitions_used = _definitions_for_fields(set(fields), definitions)
    if query.qualitative_definition == "overall_good_student":
        definitions_used["ranking"] = "active placement-readiness score; ties retain equal evidence and are shown in deterministic name order"
    obs = observation(
        kind="student_ranking" if query.goal == QueryGoal.RANK else "student_records",
        entity="student", facts={"items": projected, "total": total},
        source="Edvatiq College records", source_timestamp=source_timestamp,
        sample_size=len(rows), population_size=total, coverage_percent=coverage,
        definitions=definitions_used, authorized_scope=envelope.scope_label(total),
    )
    scope_phrase = envelope.scope_label(total)
    if query.goal == QueryGoal.RANK:
        metric = query.sort[0].field.replace("_", " ") if query.sort else "configured metric"
        leader = projected[0]
        value = leader.get(query.sort[0].field) if query.sort else None
        value_text = f" ({value:g})" if isinstance(value, (int, float)) else ""
        answer = f"{leader['name']} ranks first by {metric}{value_text} among {scope_phrase}."
        artifact_type = "ranking"
        title = f"Student ranking by {metric}"
    else:
        answer = f"I found {total} matching student{'s' if total != 1 else ''} in {scope_phrase}."
        artifact_type = "records"
        title = "Matching students"
    has_more = total > offset + len(rows)
    if has_more:
        answer += f" Showing {offset + 1}-{offset + len(rows)}."
    if unavailable:
        answer += " Fields outside your current access were omitted."

    domains = _required_domains_placeholder(set(fields))
    artifact = Artifact(
        id=identifier("artifact"), type=artifact_type, title=title,
        data={
            "items": projected, "total": total, "has_more": has_more,
            "query": query.model_dump(mode="json"),
            "scope_label": scope_phrase,
        },
        evidence_ids=[obs.id],
        security=security(
            permissions=(
                "college.students.view",
                *(["college.students.contact.view"] if set(fields) & {"email", "phone"} else []),
            ),
            domains=("students", *domains),
            entity_ids=(row["id"] for row in rows),
            scope={"population": total},
        ),
    )
    artifacts = [artifact]
    if unavailable:
        artifacts.append(Artifact(
            id=identifier("artifact"), type="notice", title="Access-limited fields",
            data={"unavailable_fields": unavailable}, security=security(permissions=("ai.use",)),
        ))
    return AssistantResponse(
        outcome=AssistantOutcome.PARTIAL if unavailable else AssistantOutcome.SUCCESS,
        answer=answer, artifacts=artifacts,
        suggestions=[Suggestion(
            id=identifier("suggestion"), label="Compare selected students",
            prompt="Compare these students' academic performance and placement readiness",
            entity_refs=[EntityRef(kind="student", id=row["id"], label=row["name"]) for row in rows[:2]],
            security=artifact.security,
        )] if len(rows) >= 2 else [],
        observations=[obs], scope=envelope.public_scope(),
    )


def _required_domains_placeholder(fields: set[str]) -> tuple[str, ...]:
    domains = []
    if fields & ACADEMIC_FIELDS:
        domains.append("assessments")
    if fields & ATTENDANCE_FIELDS:
        domains.append("attendance")
    if fields & READINESS_FIELDS:
        domains.append("readiness")
    if fields & CODING_FIELDS:
        domains.append("coding")
    if fields & PLACEMENT_FIELDS:
        domains.append("placements")
    return tuple(domains)


def _metric_value(metric: str, rows: list[dict]) -> tuple[float | int | None, int]:
    if metric == "student_count":
        return len(rows), len(rows)
    source = {
        "average_cgpa": "cgpa",
        "average_attendance": "attendance_percent",
        "average_package": "highest_package",
        "readiness_score": "readiness_score",
        "average_skill_count": "skill_count",
    }.get(metric)
    if source:
        values = [float(row[source]) for row in rows if row.get(source) is not None]
        return (round(sum(values) / len(values), 2), len(values)) if values else (None, 0)
    if metric == "placement_rate":
        known = [row for row in rows if row.get("placement_status") in {"placed", "unplaced"}]
        placed = sum(row.get("placement_status") == "placed" for row in known)
        return (round(placed * 100 / len(known), 2), len(known)) if known else (None, 0)
    if metric == "certification_total":
        values = [int(row["certification_count"]) for row in rows if row.get("certification_count") is not None]
        return (sum(values), len(values)) if values else (None, 0)
    if metric == "internship_participation_rate":
        known = [row for row in rows if row.get("internship_count") is not None]
        participated = sum(int(row["internship_count"]) > 0 for row in known)
        return (round(participated * 100 / len(known), 2), len(known)) if known else (None, 0)
    return None, 0


def _student_comparison_response(
    db: Session,
    query: SemanticQuery,
    fields: list[str],
    unavailable: list[str],
    envelope: AccessEnvelope,
    definitions: dict,
    scope_ids: set[str] | None,
) -> AssistantResponse:
    rows, _, _ = _student_dataset(db, query, set(fields), envelope, scope_ids, limit=20)
    if len(rows) < 2:
        return AssistantResponse(
            outcome=AssistantOutcome.NOT_FOUND,
            answer="I couldn't resolve two students inside your authorized scope.",
            scope=envelope.public_scope(),
        )
    comparison_fields = [key for key in fields if key not in {"id", "name"}]
    if not comparison_fields:
        comparison_fields = ["department", "program", "cohort"]
    source_timestamps = [
        row.get("source_updated_at") for row in rows if row.get("source_updated_at")
    ]
    row_ids = [row["id"] for row in rows]
    if "academic_history" in comparison_fields:
        history: dict[str, list[dict]] = defaultdict(list)
        term_results = list(db.execute(select(CollegeTermResult).where(
            CollegeTermResult.organization_id == envelope.organization_id,
            CollegeTermResult.student_profile_id.in_(row_ids),
            CollegeTermResult.result_status == "published",
        ).order_by(
            CollegeTermResult.student_profile_id,
            CollegeTermResult.semester,
            CollegeTermResult.published_on,
        )).scalars())
        for result in term_results:
            history[result.student_profile_id].append({
                "semester": result.semester,
                "sgpa": float(result.sgpa) if result.sgpa is not None else None,
                "cgpa": float(result.cgpa) if result.cgpa is not None else None,
                "active_backlogs": result.active_backlogs,
                "published_on": result.published_on,
            })
            source_timestamps.append(result.updated_at)
        for row in rows:
            row["academic_history"] = json_value(history.get(row["id"], []))
    if "attendance_history" in comparison_fields:
        history = defaultdict(list)
        attendance_rows = list(db.execute(select(CollegeAttendanceSnapshot).where(
            CollegeAttendanceSnapshot.organization_id == envelope.organization_id,
            CollegeAttendanceSnapshot.student_profile_id.in_(row_ids),
            CollegeAttendanceSnapshot.course_id.is_(None),
        ).order_by(
            CollegeAttendanceSnapshot.student_profile_id,
            CollegeAttendanceSnapshot.as_of,
        )).scalars())
        for snapshot in attendance_rows:
            history[snapshot.student_profile_id].append({
                "attendance_percent": (
                    float(snapshot.attendance_percent)
                    if snapshot.attendance_percent is not None else None
                ),
                "classes_held": snapshot.classes_held,
                "classes_attended": snapshot.classes_attended,
                "as_of": snapshot.as_of,
            })
            source_timestamps.append(snapshot.updated_at)
        for row in rows:
            row["attendance_history"] = json_value(history.get(row["id"], []))
    items = [{
        "id": row["id"], "name": row["name"],
        "values": {key: row.get(key) for key in comparison_fields},
    } for row in rows[:20]]
    observations = [observation(
        kind="student_comparison", entity="student",
        facts={"items": items}, source="Edvatiq College records",
        source_timestamp=max((item for item in source_timestamps if item), default=None),
        sample_size=len(items), population_size=len(items),
        definitions=_definitions_for_fields(set(comparison_fields), definitions),
        authorized_scope=envelope.scope_label(len(items)),
    )]
    first_field = next((key for key in comparison_fields if all(isinstance(item["values"].get(key), (int, float)) for item in items[:2])), None)
    if "academic_history" in comparison_fields:
        answer = f"I compared the published semester-wise academic records for {len(items)} authorized students."
    elif "attendance_history" in comparison_fields:
        answer = f"I compared the recorded attendance periods for {len(items)} authorized students."
    elif first_field:
        winner = max(items[:2], key=lambda item: item["values"][first_field])
        answer = f"{winner['name']} has the higher {first_field.replace('_', ' ')} in the current verified records."
    else:
        answer = f"I compared {len(items)} authorized students using the requested verified fields."
    if unavailable:
        answer += " Fields outside your access were omitted."
    artifact = Artifact(
        id=identifier("artifact"), type="comparison", title="Student comparison",
        data={"items": items, "fields": comparison_fields},
        evidence_ids=[item.id for item in observations],
        security=security(
            permissions=("college.students.view",),
            domains=("students", *_required_domains_placeholder(set(comparison_fields))),
            entity_ids=(row["id"] for row in rows),
        ),
    )
    return AssistantResponse(
        outcome=AssistantOutcome.PARTIAL if unavailable else AssistantOutcome.SUCCESS,
        answer=answer,
        artifacts=[artifact], observations=observations, scope=envelope.public_scope(),
    )


def _student_aggregate_response(
    db: Session,
    query: SemanticQuery,
    fields: list[str],
    envelope: AccessEnvelope,
    definitions: dict,
    scope_ids: set[str] | None,
    *,
    background: bool = False,
) -> AssistantResponse:
    if query.requested_analysis == "academic_weakness_definition_required":
        options = [
            {"label": "Low CGPA", "prompt": "Which classes have the lowest average CGPA?"},
            {"label": "Active backlogs", "prompt": "Compare classes by students with active backlogs."},
            {"label": "Subject failures", "prompt": "Compare classes by subject failure rate."},
        ]
        return AssistantResponse(
            outcome=AssistantOutcome.CLARIFICATION,
            answer=(
                "'Academically weak' needs an explicit governed measure. Choose low CGPA, active backlogs, "
                "subject failures, or ask an administrator to configure another safe definition."
            ),
            artifacts=[Artifact(
                id=identifier("artifact"), type="clarification", title="Choose an academic support measure",
                data={"reason": "academic_weakness_definition_required", "options": options},
                security=security(
                    permissions=("college.students.view",), domains=("students", "assessments"),
                ),
            )],
            suggestions=[Suggestion(
                id=identifier("suggestion"), label=item["label"], prompt=item["prompt"],
                security=security(
                    permissions=("college.students.view",), domains=("students", "assessments"),
                ),
            ) for item in options],
            scope=envelope.public_scope(),
        )
    row_limit = 50000 if background else 5000
    rows, total, _ = _student_dataset(
        db, query, set(fields), envelope, scope_ids,
        limit=row_limit, hard_limit=row_limit,
    )
    if total > row_limit:
        return AssistantResponse(
            outcome=AssistantOutcome.UNAVAILABLE if background else AssistantOutcome.PROCESSING,
            answer=(
                "This analysis exceeds the background safety limit. Narrow the population or time range."
                if background else
                "This analysis is larger than the interactive safety limit. I've queued it as an authorized background analysis."
            ),
            artifacts=[] if background else [Artifact(
                id=identifier("artifact"), type="processing", title="Analysis queued",
                data={"population": total, "query": query.model_dump(mode="json")},
                security=security(
                    permissions=("college.students.view",), domains=("students",),
                    scope={"population": total},
                ),
            )], scope=envelope.public_scope(),
        )
    if not rows:
        return AssistantResponse(
            outcome=AssistantOutcome.EMPTY,
            answer="There are no records in your authorized scope for this analysis.",
            scope=envelope.public_scope(),
        )
    groups: dict[str, list[dict]] = defaultdict(list)
    group_fields = query.group_by
    if group_fields:
        for row in rows:
            key = " / ".join(str(row.get(field) or "Unknown") for field in group_fields)
            groups[key].append(row)
    else:
        groups[envelope.scope_label(total)] = rows

    metrics = query.metrics or ["student_count"]
    results = []
    for label, group_rows in groups.items():
        values, coverage = {}, {}
        for metric in metrics:
            value, sample = _metric_value(metric, group_rows)
            values[metric] = value
            coverage[metric] = {
                "sample_size": sample,
                "population_size": len(group_rows),
                "coverage_percent": round(sample * 100 / len(group_rows), 1) if group_rows else 0,
            }
        results.append({"group": label, "values": values, "coverage": coverage, "population": len(group_rows)})
    primary = metrics[0]
    ascending = query.requested_analysis == "aggregate_ascending" or bool(
        query.sort and query.sort[0].direction == "asc"
    )
    if ascending:
        results.sort(key=lambda item: (
            item["values"].get(primary) is None,
            item["values"].get(primary) if item["values"].get(primary) is not None else math.inf,
            item["group"].casefold(),
        ))
    else:
        results.sort(key=lambda item: (
            item["values"].get(primary) is None,
            -(item["values"].get(primary) if item["values"].get(primary) is not None else -math.inf),
            item["group"].casefold(),
        ))

    obs = observation(
        kind="student_aggregate", entity="student",
        facts={"groups": results, "metrics": metrics},
        source="Edvatiq College records", sample_size=len(rows), population_size=total,
        definitions={
            "population": f"Only students inside {envelope.scope_label(total)} are included",
            "placement rate": "placed or joined students divided by students with authorized placement status",
            **_definitions_for_fields(set(fields), definitions),
        },
        authorized_scope=envelope.scope_label(total),
    )
    if len(results) > 1:
        leader = results[0]
        value = leader["values"].get(primary)
        direction = "lowest" if ascending else "highest"
        answer = f"{leader['group']} has the {direction} {primary.replace('_', ' ')}"
        if value is not None:
            answer += f" at {value:g}"
        answer += f" among {envelope.scope_label(total)}."
    else:
        value = results[0]["values"].get(primary)
        answer = f"The {primary.replace('_', ' ')} is {value:g} across {envelope.scope_label(total)}." if value is not None else (
            f"There is not enough evidence to calculate {primary.replace('_', ' ')} across {envelope.scope_label(total)}."
        )
    artifact = Artifact(
        id=identifier("artifact"), type="comparison" if len(results) > 1 else "metric",
        title="College analysis", data={"groups": results, "metrics": metrics, "total": total},
        evidence_ids=[obs.id],
        security=security(
            permissions=("college.students.view",),
            domains=("students", *_required_domains_placeholder(set(fields))),
            entity_ids=(row["id"] for row in rows), scope={"population": total},
        ),
    )
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS if any(item["values"].get(primary) is not None for item in results) else AssistantOutcome.INSUFFICIENT_EVIDENCE,
        answer=answer, artifacts=[artifact], observations=[obs], scope=envelope.public_scope(),
    )


def _correlation_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
    definitions: dict,
    scope_ids: set[str] | None,
    *,
    background: bool = False,
) -> AssistantResponse:
    row_limit = 50000 if background else 5000
    rows, total, _ = _student_dataset(
        db, query, {"cgpa", "attendance_percent"}, envelope, scope_ids,
        limit=row_limit, hard_limit=row_limit,
    )
    if total > row_limit:
        return AssistantResponse(
            outcome=AssistantOutcome.UNAVAILABLE if background else AssistantOutcome.PROCESSING,
            answer=(
                "This correlation analysis exceeds the background safety limit. Narrow the population or time range."
                if background else
                "This correlation analysis exceeds the interactive limit and has been queued as an authorized background job."
            ),
            artifacts=[] if background else [Artifact(
                id=identifier("artifact"), type="processing", title="Correlation analysis queued",
                data={"authorized_population": total, "query": query.model_dump(mode="json")},
                security=security(
                    permissions=("college.assessments.view", "college.attendance.view"),
                    domains=("assessments", "attendance"), scope={"population": total},
                ),
            )], scope=envelope.public_scope(),
        )
    pairs = [(float(row["attendance_percent"]), float(row["cgpa"])) for row in rows if row.get("attendance_percent") is not None and row.get("cgpa") is not None]
    minimum = int(definitions["minimum_association_sample"])
    if len(pairs) < minimum:
        return AssistantResponse(
            outcome=AssistantOutcome.INSUFFICIENT_EVIDENCE,
            answer=f"Only {len(pairs)} authorized students have both attendance and CGPA evidence; at least {minimum} are required for this association analysis.",
            artifacts=[Artifact(
                id=identifier("artifact"), type="notice", title="Insufficient paired evidence",
                data={"paired_sample": len(pairs), "required_sample": minimum, "authorized_population": total},
                security=security(
                    permissions=("college.attendance.view", "college.assessments.view"),
                    domains=("students", "attendance", "assessments"),
                ),
            )], scope=envelope.public_scope(),
        )
    xs, ys = zip(*pairs)
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denominator = math.sqrt(sum((x - mean_x) ** 2 for x in xs) * sum((y - mean_y) ** 2 for y in ys))
    coefficient = numerator / denominator if denominator else 0.0
    strength = "weak" if abs(coefficient) < 0.3 else "moderate" if abs(coefficient) < 0.6 else "strong"
    direction = "positive" if coefficient > 0 else "negative" if coefficient < 0 else "no linear"
    obs = observation(
        kind="historical_association", entity="student",
        facts={"pearson_r": round(coefficient, 3), "paired_sample": len(pairs), "authorized_population": total},
        source="Edvatiq College attendance and term results",
        sample_size=len(pairs), population_size=total,
        coverage_percent=round(len(pairs) * 100 / total, 1) if total else 0,
        definitions={"interpretation": "historical linear association; not a causal effect"},
        authorized_scope=envelope.scope_label(total),
    )
    answer = (
        f"The authorized historical data shows a {strength} {direction} association between attendance and CGPA "
        f"(r={coefficient:.2f}, n={len(pairs)}). This is descriptive, not evidence that attendance causes the academic result."
    )
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS, answer=answer,
        artifacts=[Artifact(
            id=identifier("artifact"), type="chart", title="Attendance and CGPA association",
            data={"chart_type": "scatter", "x": "attendance_percent", "y": "cgpa", "rows": [{"attendance_percent": x, "cgpa": y} for x, y in pairs[:500]], "pearson_r": round(coefficient, 3)},
            evidence_ids=[obs.id],
            security=security(
                permissions=("college.attendance.view", "college.assessments.view"),
                domains=("students", "attendance", "assessments"),
                entity_ids=(row["id"] for row in rows),
                scope={"population": total},
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _trend_response(
    db: Session,
    query: SemanticQuery,
    envelope: AccessEnvelope,
    definitions: dict,
    scope_ids: set[str] | None,
    *,
    background: bool = False,
) -> AssistantResponse:
    analysis = query.requested_analysis or "academic_change"
    candidate_fields = {"id", "name", "department", "program", "cohort", "graduation_year"}
    candidate_query = query.model_copy(update={
        "fields": sorted(candidate_fields),
        "metrics": [],
        "group_by": [],
        "sort": [],
        "filters": [item for item in query.filters if item.field != "improvement"],
        "limit": 100,
    })
    candidate_limit = 50000 if background else 5000
    candidates, total, _ = _student_dataset(
        db, candidate_query, candidate_fields, envelope, scope_ids,
        limit=candidate_limit, hard_limit=candidate_limit,
    )
    if total > candidate_limit:
        return AssistantResponse(
            outcome=AssistantOutcome.UNAVAILABLE if background else AssistantOutcome.PROCESSING,
            answer=(
                "This trend exceeds the background population safety limit. Narrow the population."
                if background else
                "This trend exceeds the interactive population limit and has been queued for authorized background analysis."
            ),
            artifacts=[] if background else [Artifact(
                id=identifier("artifact"), type="processing", title="Trend analysis queued",
                data={"authorized_population": total, "query": query.model_dump(mode="json")},
                security=security(
                    permissions=("college.students.view",), domains=("students",),
                    scope={"population": total},
                ),
            )],
            scope=envelope.public_scope(),
        )
    if not candidates:
        return AssistantResponse(
            outcome=AssistantOutcome.EMPTY,
            answer="There are no students in the authorized population for this trend analysis.",
            scope=envelope.public_scope(),
        )

    candidate_ids = [item["id"] for item in candidates]
    if analysis in {"attendance_change", "attendance_drop", "consistent_attendance"}:
        statement = select(CollegeAttendanceSnapshot).where(
            CollegeAttendanceSnapshot.organization_id == envelope.organization_id,
            CollegeAttendanceSnapshot.course_id.is_(None),
            CollegeAttendanceSnapshot.student_profile_id.in_(candidate_ids),
        )
        model_field = "attendance_percent"
        order_field = CollegeAttendanceSnapshot.as_of
        period_field = "as_of"
        domain = "attendance"
        permission = "college.attendance.view"
        required_periods = (
            int(definitions["consistent_attendance_periods"])
            if analysis == "consistent_attendance"
            else int(definitions["improvement_periods"])
        )
    elif analysis == "readiness_change":
        policy = _readiness_policy(db, envelope.organization_id)
        if not policy:
            return AssistantResponse(
                outcome=AssistantOutcome.CONFIGURATION_REQUIRED,
                answer="An active placement-readiness policy is required for this trend.",
                scope=envelope.public_scope(),
            )
        statement = select(CollegeReadinessSnapshot).where(
            CollegeReadinessSnapshot.organization_id == envelope.organization_id,
            CollegeReadinessSnapshot.policy_id == policy.id,
            CollegeReadinessSnapshot.student_profile_id.in_(candidate_ids),
        )
        model_field = "score"
        order_field = CollegeReadinessSnapshot.calculated_at
        period_field = "calculated_at"
        domain = "readiness"
        permission = "college.readiness.view"
        required_periods = int(definitions["improvement_periods"])
    else:
        statement = select(CollegeTermResult).where(
            CollegeTermResult.organization_id == envelope.organization_id,
            CollegeTermResult.result_status == "published",
            CollegeTermResult.student_profile_id.in_(candidate_ids),
        )
        model_field = "cgpa"
        order_field = CollegeTermResult.semester
        period_field = "semester"
        domain = "assessments"
        permission = "college.assessments.view"
        required_periods = int(definitions["improvement_periods"])
    student_expression = {
        "attendance": CollegeAttendanceSnapshot.student_profile_id,
        "readiness": CollegeReadinessSnapshot.student_profile_id,
        "assessments": CollegeTermResult.student_profile_id,
    }[domain]
    history_limit = 500000 if background else 50000
    history = list(db.execute(statement.order_by(
        student_expression,
        order_field.desc(),
    ).limit(history_limit + 1)).scalars())
    if len(history) > history_limit:
        return AssistantResponse(
            outcome=AssistantOutcome.UNAVAILABLE if background else AssistantOutcome.PROCESSING,
            answer=(
                "This trend exceeds the background history safety limit. Narrow the population or time range."
                if background else
                "This trend has too much period history for an interactive answer and has been queued for background analysis."
            ),
            artifacts=[] if background else [Artifact(
                id=identifier("artifact"), type="processing", title="Trend history queued",
                data={"authorized_population": total, "history_limit": history_limit},
                security=security(
                    permissions=(permission,), domains=("students", domain),
                    scope={"population": total},
                ),
            )],
            scope=envelope.public_scope(),
        )
    by_student: dict[str, list] = defaultdict(list)
    seen_periods: dict[str, set] = defaultdict(set)
    for row in history:
        period = getattr(row, period_field)
        if period in seen_periods[row.student_profile_id]:
            continue
        seen_periods[row.student_profile_id].add(period)
        by_student[row.student_profile_id].append(row)
    changes = []
    for student_id, values in by_student.items():
        comparable = [row for row in values if getattr(row, model_field) is not None]
        if len(comparable) < required_periods:
            continue
        selected = comparable[:required_periods]
        current, previous = selected[0], selected[1]
        change = round(float(getattr(current, model_field)) - float(getattr(previous, model_field)), 2)
        if analysis == "attendance_drop" and change > -float(definitions["sudden_attendance_drop_points"]):
            continue
        if analysis == "consistent_attendance" and any(
            float(getattr(row, model_field)) < float(definitions["consistent_attendance_percent"])
            for row in selected
        ):
            continue
        item = {
            "id": student_id,
            "current": float(getattr(current, model_field)),
            "previous": float(getattr(previous, model_field)),
            "change": change,
            "periods": required_periods,
        }
        if analysis == "consistent_attendance":
            period_values = [float(getattr(row, model_field)) for row in selected]
            item.update({
                "minimum": round(min(period_values), 2),
                "average": round(sum(period_values) / len(period_values), 2),
            })
        changes.append(item)
    if not changes:
        detail = (
            f" meeting at least {float(definitions['consistent_attendance_percent']):g}% across "
            f"{required_periods} comparable periods"
            if analysis == "consistent_attendance" else
            f" with a drop of at least {float(definitions['sudden_attendance_drop_points']):g} percentage points"
            if analysis == "attendance_drop" else
            " with enough comparable evidence"
        )
        return AssistantResponse(
            outcome=AssistantOutcome.INSUFFICIENT_EVIDENCE,
            answer=f"I couldn't find authorized students{detail} for this trend analysis.",
            scope=envelope.public_scope(),
        )
    candidate_by_id = {item["id"]: item for item in candidates}
    for item in changes:
        candidate = candidate_by_id[item["id"]]
        item.update({
            "name": candidate.get("name") or "Student",
            "department": candidate.get("department"),
            "program": candidate.get("program"),
            "cohort": candidate.get("cohort"),
        })

    if analysis == "academic_period_comparison" and not query.group_by:
        current_average = sum(item["current"] for item in changes) / len(changes)
        previous_average = sum(item["previous"] for item in changes) / len(changes)
        result_items = [{
            "group": envelope.scope_label(total),
            "current": round(current_average, 2),
            "previous": round(previous_average, 2),
            "change": round(current_average - previous_average, 2),
            "student_count": len(changes),
        }]
        artifact_type = "comparison"
        title = "Current and previous academic periods"
        answer = (
            f"Across {len(changes)} students with comparable authorized results, average CGPA changed "
            f"from {previous_average:.2f} to {current_average:.2f} ({current_average - previous_average:+.2f})."
        )
        result_ids = [item["id"] for item in changes]
    elif query.group_by:
        grouped: dict[str, list[dict]] = defaultdict(list)
        for item in changes:
            label = " / ".join(str(item.get(field) or "Unknown") for field in query.group_by)
            grouped[label].append(item)
        result_items = []
        for label, items in grouped.items():
            current_average = sum(item["current"] for item in items) / len(items)
            previous_average = sum(item["previous"] for item in items) / len(items)
            result_items.append({
                "group": label,
                "current": round(current_average, 2),
                "previous": round(previous_average, 2),
                "change": round(current_average - previous_average, 2),
                "student_count": len(items),
            })
        result_items.sort(key=lambda item: (-item["change"], item["group"].casefold()))
        result_items = result_items[:query.limit]
        leader = result_items[0]
        artifact_type = "ranking"
        title = "Academic change by group"
        answer = (
            f"{leader['group']} shows the largest average {model_field.replace('_', ' ')} change at "
            f"{leader['change']:+.2f} among {envelope.scope_label(total)}."
        )
        result_ids = [item["id"] for item in changes]
    else:
        if analysis == "attendance_drop":
            changes.sort(key=lambda item: (item["change"], item["name"].casefold()))
        elif analysis == "consistent_attendance":
            changes.sort(key=lambda item: (-item["average"], item["name"].casefold()))
        else:
            changes.sort(key=lambda item: (-item["change"], item["name"].casefold()))
        result_items = changes[:query.limit]
        leader = result_items[0]
        artifact_type = "ranking"
        result_ids = [item["id"] for item in result_items]
        if analysis == "attendance_drop":
            title = "Sudden attendance drops"
            answer = (
                f"{leader['name']} has the largest verified attendance drop at "
                f"{abs(leader['change']):.2f} percentage points across the latest two comparable periods."
            )
        elif analysis == "consistent_attendance":
            title = "Consistently high attendance"
            answer = (
                f"{len(changes)} students maintained at least "
                f"{float(definitions['consistent_attendance_percent']):g}% attendance across their latest "
                f"{required_periods} comparable periods."
            )
        else:
            title = "Most improved students"
            answer = (
                f"{leader['name']} shows the largest {model_field.replace('_', ' ')} improvement at "
                f"{leader['change']:+.2f} across the latest two comparable periods."
            )

    source_timestamp = max(
        (row.updated_at for row in history if getattr(row, "updated_at", None)),
        default=None,
    )
    definitions_used = {"comparison": f"latest {required_periods} distinct comparable periods"}
    if analysis == "attendance_drop":
        definitions_used["sudden attendance drop"] = (
            f"at least {float(definitions['sudden_attendance_drop_points']):g} percentage points"
        )
    elif analysis == "consistent_attendance":
        definitions_used["consistent attendance"] = (
            f"at least {float(definitions['consistent_attendance_percent']):g}% across {required_periods} periods"
        )
    obs = observation(
        kind="student_trend", entity="student", facts={"items": result_items, "measure": model_field},
        source="Edvatiq College period records", source_timestamp=source_timestamp,
        sample_size=len(changes), population_size=total,
        coverage_percent=round(len(changes) * 100 / total, 1) if total else 0,
        definitions=definitions_used,
        authorized_scope=envelope.scope_label(total),
    )
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS, answer=answer,
        artifacts=[Artifact(
            id=identifier("artifact"), type=artifact_type, title=title,
            data={"items": result_items, "measure": model_field, "authorized_population": total},
            evidence_ids=[obs.id],
            security=security(
                permissions=(permission,), domains=("students", domain),
                entity_ids=result_ids, scope={"population": total},
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )
