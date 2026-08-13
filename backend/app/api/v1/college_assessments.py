"""Institution-configured College assessment patterns and exam cycles."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field, model_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_entitlements, require_permissions
from app.models import (
    CollegeAssessment,
    CollegeAssessmentComponent,
    CollegeAssessmentReadinessMapping,
    CollegeAssessmentScheme,
    CollegeAssessmentSchemeAssignment,
    CollegeCohort,
    CollegeCourseOffering,
    CollegeExamCycle,
    User,
)
from app.schemas.validation import RequestModel
from app.services.audit import log_action
from app.services.college import require_college, tenant_row
from app.services.college_access import CollegeAccess, resolve_college_access, validate_college_filters
from app.services.college_assessments import (
    SCHEME_DOMAINS,
    assignment_scope_key,
    build_scheme_snapshot,
    component_payload,
    ensure_scheme_mutable,
    freeze_scheme,
    load_scheme_bundle,
    normalize_code,
    resolve_effective_scheme,
    scheme_payload,
    validate_assignment_scope,
    validate_component_definitions,
)
from app.services.cursor_pagination import decode_cursor, encode_cursor, page_response, page_size


router = APIRouter(
    prefix="/college",
    tags=["college-assessments"],
    dependencies=[Depends(require_entitlements("module.college"))],
)


def _require_institution_configuration(access: CollegeAccess, label: str) -> None:
    if not access.unrestricted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Whole-institution access is required to manage {label}")

SchemeDomain = Literal["academic", "coding", "placement"]
MetricType = Literal["number", "percentage", "integer", "boolean", "short_text", "grade", "rank", "count"]
CalculationMethod = Literal["weighted_sum", "average", "best_n"]
ReadinessFactor = Literal["academics", "coding", "assessment", "profile", "attendance", "training"]


class SchemeComponentBody(RequestModel):
    name: str = Field(min_length=2, max_length=140)
    code: str | None = Field(default=None, max_length=50)
    component_type: str = Field(default="assessment", min_length=2, max_length=50)
    metric_type: MetricType = "number"
    display_order: int | None = Field(default=None, ge=1, le=100)
    max_marks: Decimal | None = Field(default=None, gt=0, le=1_000_000, max_digits=10, decimal_places=2)
    weightage_bps: int = Field(default=0, ge=0, le=10000)
    pass_marks: Decimal | None = Field(default=None, ge=0, le=1_000_000, max_digits=10, decimal_places=2)
    is_required: bool = True
    aggregation_group: str | None = Field(default=None, max_length=50)
    settings: dict = Field(default_factory=dict)


class SchemeBody(RequestModel):
    name: str = Field(min_length=2, max_length=180)
    code: str = Field(min_length=2, max_length=50)
    domain: SchemeDomain = "academic"
    description: str | None = Field(default=None, max_length=2000)
    final_score_max: Decimal = Field(default=Decimal("100"), gt=0, le=1_000_000, max_digits=10, decimal_places=2)
    calculation_method: CalculationMethod = "weighted_sum"
    calculation_config: dict = Field(default_factory=dict)
    components: list[SchemeComponentBody] = Field(min_length=1, max_length=100)
    activate: bool = False


class SchemePatchBody(RequestModel):
    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=2000)
    final_score_max: Decimal | None = Field(default=None, gt=0, le=1_000_000, max_digits=10, decimal_places=2)
    calculation_method: CalculationMethod | None = None
    calculation_config: dict | None = None
    components: list[SchemeComponentBody] | None = Field(default=None, min_length=1, max_length=100)
    activate: bool | None = None


class SchemeVersionBody(RequestModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=2000)
    final_score_max: Decimal | None = Field(default=None, gt=0, le=1_000_000, max_digits=10, decimal_places=2)
    calculation_method: CalculationMethod | None = None
    calculation_config: dict | None = None
    components: list[SchemeComponentBody] | None = Field(default=None, min_length=1, max_length=100)
    activate: bool = False


class SchemeAssignmentBody(RequestModel):
    program_id: str | None = None
    cohort_id: str | None = None
    term_id: str | None = None


class ReadinessMappingBody(RequestModel):
    metric_code: str = Field(min_length=2, max_length=50)
    factor_key: ReadinessFactor
    is_active: bool = True
    version: int | None = Field(default=None, ge=1)


class ExamCycleBody(RequestModel):
    scheme_id: str
    scheme_component_id: str | None = None
    term_id: str | None = None
    name: str = Field(min_length=2, max_length=180)
    code: str = Field(min_length=2, max_length=60)
    held_on: date | None = None
    due_on: date | None = None
    offering_ids: list[str] = Field(default_factory=list, max_length=500)
    cohort_ids: list[str] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def valid_dates_and_targets(self):
        if self.held_on and self.due_on and self.due_on < self.held_on:
            raise ValueError("Due date cannot be before the assessment date")
        if len(set(self.offering_ids)) != len(self.offering_ids) or len(set(self.cohort_ids)) != len(self.cohort_ids):
            raise ValueError("Each target can appear only once")
        return self


def _component_dicts(items: list[SchemeComponentBody]) -> list[dict]:
    return [item.model_dump() for item in items]


def _replace_components(
    db: Session,
    scheme: CollegeAssessmentScheme,
    definitions: list[dict],
) -> list[CollegeAssessmentComponent]:
    old = list(db.scalars(select(CollegeAssessmentComponent).where(
        CollegeAssessmentComponent.organization_id == scheme.organization_id,
        CollegeAssessmentComponent.scheme_id == scheme.id,
    )))
    for item in old:
        db.delete(item)
    db.flush()
    rows = [CollegeAssessmentComponent(
        organization_id=scheme.organization_id,
        scheme_id=scheme.id,
        **definition,
    ) for definition in definitions]
    db.add_all(rows)
    db.flush()
    return rows


def _commit_scheme(db: Session, user: User, scheme: CollegeAssessmentScheme, action: str, changes: dict | None = None) -> dict:
    try:
        db.flush()
        log_action(
            db,
            organization_id=user.organization_id,
            user_id=user.id,
            action=action,
            resource_type="college_assessment_schemes",
            resource_id=scheme.id,
            permission="college.academics.manage",
            changes=changes or {},
        )
        db.commit()
        scheme, components, assignments = load_scheme_bundle(db, user.organization_id, scheme.id)
        return scheme_payload(scheme, components, assignments)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This pattern code, version, or assignment already exists") from exc


def _readiness_mapping_payload(row: CollegeAssessmentReadinessMapping) -> dict:
    return {
        "id": row.id,
        "scheme_id": row.scheme_id,
        "metric_code": row.metric_code,
        "factor_key": row.factor_key,
        "is_active": row.is_active,
        "version": row.version,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("/assessment-schemes/page")
def assessment_schemes_page(
    q: str | None = Query(default=None, max_length=120),
    domain: SchemeDomain | None = None,
    scheme_status: Literal["draft", "active", "frozen", "retired"] | None = Query(default=None, alias="status"),
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_permissions("college.academics.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    resolve_college_access(db, user, "academics")
    filters = {"q": q, "domain": domain, "status": scheme_status}
    values = decode_cursor(cursor, scope="college.assessment-schemes", organization_id=user.organization_id, filters=filters)
    statement = select(CollegeAssessmentScheme).where(CollegeAssessmentScheme.organization_id == user.organization_id)
    if q:
        term = f"%{' '.join(q.casefold().split())}%"
        statement = statement.where(func.lower(func.concat_ws(" ", CollegeAssessmentScheme.name, CollegeAssessmentScheme.code)).like(term))
    if domain:
        statement = statement.where(CollegeAssessmentScheme.domain == domain)
    if scheme_status:
        statement = statement.where(CollegeAssessmentScheme.status == scheme_status)
    if values:
        at = datetime.fromisoformat(str(values["at"]))
        row_id = str(values["id"])
        statement = statement.where(or_(
            CollegeAssessmentScheme.created_at < at,
            and_(CollegeAssessmentScheme.created_at == at, CollegeAssessmentScheme.id < row_id),
        ))
    size = page_size(limit)
    rows = list(db.scalars(statement.order_by(
        CollegeAssessmentScheme.created_at.desc(), CollegeAssessmentScheme.id.desc(),
    ).limit(size + 1)))
    has_more = len(rows) > size
    rows = rows[:size]
    ids = [row.id for row in rows]
    components = list(db.scalars(select(CollegeAssessmentComponent).where(
        CollegeAssessmentComponent.scheme_id.in_(ids),
        CollegeAssessmentComponent.organization_id == user.organization_id,
    ).order_by(CollegeAssessmentComponent.display_order))) if ids else []
    assignments = list(db.scalars(select(CollegeAssessmentSchemeAssignment).where(
        CollegeAssessmentSchemeAssignment.scheme_id.in_(ids),
        CollegeAssessmentSchemeAssignment.organization_id == user.organization_id,
    ))) if ids else []
    components_by_scheme: dict[str, list] = {}
    assignments_by_scheme: dict[str, list] = {}
    for item in components:
        components_by_scheme.setdefault(item.scheme_id, []).append(item)
    for item in assignments:
        assignments_by_scheme.setdefault(item.scheme_id, []).append(item)
    items = [scheme_payload(row, components_by_scheme.get(row.id, []), assignments_by_scheme.get(row.id, [])) for row in rows]
    next_cursor = encode_cursor(
        scope="college.assessment-schemes",
        organization_id=user.organization_id,
        filters=filters,
        values={"at": rows[-1].created_at.isoformat(), "id": rows[-1].id},
    ) if has_more and rows else None
    return page_response(items, next_cursor)


@router.post("/assessment-schemes", status_code=201)
def create_assessment_scheme(
    body: SchemeBody,
    user: User = Depends(require_permissions("college.academics.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    _require_institution_configuration(resolve_college_access(db, user, "academics"), "assessment patterns")
    definitions = validate_component_definitions(
        _component_dicts(body.components), body.calculation_method, body.calculation_config,
    )
    scheme = CollegeAssessmentScheme(
        organization_id=user.organization_id,
        name=body.name,
        code=normalize_code(body.code, max_length=50),
        domain=body.domain,
        description=body.description,
        final_score_max=body.final_score_max,
        calculation_method=body.calculation_method,
        calculation_config=body.calculation_config,
        status="active" if body.activate else "draft",
    )
    db.add(scheme)
    db.flush()
    _replace_components(db, scheme, definitions)
    return _commit_scheme(db, user, scheme, "college.assessment_scheme.create")


@router.patch("/assessment-schemes/{scheme_id}")
def update_assessment_scheme(
    scheme_id: str,
    body: SchemePatchBody,
    user: User = Depends(require_permissions("college.academics.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    _require_institution_configuration(resolve_college_access(db, user, "academics"), "assessment patterns")
    scheme, components, _assignments = load_scheme_bundle(db, user.organization_id, scheme_id)
    if scheme.version != body.version:
        raise HTTPException(status.HTTP_409_CONFLICT, "This assessment pattern changed. Refresh and try again")
    ensure_scheme_mutable(db, scheme)
    method = body.calculation_method or scheme.calculation_method
    config = body.calculation_config if body.calculation_config is not None else scheme.calculation_config
    component_input = _component_dicts(body.components) if body.components is not None else [component_payload(item) for item in components]
    definitions = validate_component_definitions(component_input, method, config)
    before = scheme_payload(scheme, components, [])
    for field in ("name", "description", "final_score_max", "calculation_method", "calculation_config"):
        if field in body.model_fields_set:
            setattr(scheme, field, getattr(body, field))
    if body.activate is not None:
        scheme.status = "active" if body.activate else "draft"
    if body.components is not None:
        _replace_components(db, scheme, definitions)
    scheme.version += 1
    return _commit_scheme(db, user, scheme, "college.assessment_scheme.update", {"before": before})


@router.post("/assessment-schemes/{scheme_id}/versions", status_code=201)
def create_assessment_scheme_version(
    scheme_id: str,
    body: SchemeVersionBody,
    user: User = Depends(require_permissions("college.academics.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    _require_institution_configuration(resolve_college_access(db, user, "academics"), "assessment patterns")
    source, components, _assignments = load_scheme_bundle(db, user.organization_id, scheme_id)
    method = body.calculation_method or source.calculation_method
    config = body.calculation_config if body.calculation_config is not None else source.calculation_config
    definitions = validate_component_definitions(
        _component_dicts(body.components) if body.components is not None else [component_payload(item) for item in components],
        method,
        config,
    )
    latest = db.scalar(select(func.max(CollegeAssessmentScheme.version_number)).where(
        CollegeAssessmentScheme.organization_id == user.organization_id,
        CollegeAssessmentScheme.code == source.code,
    )) or source.version_number
    scheme = CollegeAssessmentScheme(
        organization_id=user.organization_id,
        name=body.name or source.name,
        code=source.code,
        domain=source.domain,
        description=body.description if body.description is not None else source.description,
        version_number=int(latest) + 1,
        supersedes_scheme_id=source.id,
        status="active" if body.activate else "draft",
        final_score_max=body.final_score_max or source.final_score_max,
        calculation_method=method,
        calculation_config=config,
    )
    db.add(scheme)
    db.flush()
    _replace_components(db, scheme, definitions)
    return _commit_scheme(db, user, scheme, "college.assessment_scheme.version.create", {"source_scheme_id": source.id})


@router.post("/assessment-schemes/{scheme_id}/assignments", status_code=201)
def assign_assessment_scheme(
    scheme_id: str,
    body: SchemeAssignmentBody,
    user: User = Depends(require_permissions("college.academics.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "academics")
    if body.program_id:
        access.require_program(body.program_id)
    if body.cohort_id:
        access.require_cohort(body.cohort_id)
    if not body.program_id and not body.cohort_id:
        _require_institution_configuration(access, "institution assessment-pattern assignments")
    scheme, components, _assignments = load_scheme_bundle(db, user.organization_id, scheme_id)
    if scheme.status not in {"active", "frozen"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Activate this pattern before assigning it")
    if not components:
        raise HTTPException(status.HTTP_409_CONFLICT, "This pattern has no components")
    validate_assignment_scope(
        db, user.organization_id,
        program_id=body.program_id, cohort_id=body.cohort_id, term_id=body.term_id,
    )
    scope_key = assignment_scope_key(
        scheme.domain,
        program_id=body.program_id,
        cohort_id=body.cohort_id,
        term_id=body.term_id,
    )
    existing = db.scalar(select(CollegeAssessmentSchemeAssignment).where(
        CollegeAssessmentSchemeAssignment.organization_id == user.organization_id,
        CollegeAssessmentSchemeAssignment.scope_key == scope_key,
    ))
    if existing:
        if existing.scheme_id == scheme.id and existing.is_active:
            return {
                "id": existing.id, "scheme_id": existing.scheme_id,
                "scope_key": existing.scope_key, "version": existing.version,
            }
        assigned_scheme = db.scalar(select(CollegeAssessmentScheme).where(
            CollegeAssessmentScheme.id == existing.scheme_id,
            CollegeAssessmentScheme.organization_id == user.organization_id,
        ))
        if not assigned_scheme or assigned_scheme.code != scheme.code:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "A different assessment pattern owns this scope. Review that assignment before replacing it.",
            )
        before_scheme_id = existing.scheme_id
        existing.scheme_id = scheme.id
        existing.is_active = True
        existing.version += 1
        db.flush()
        log_action(
            db, organization_id=user.organization_id, user_id=user.id,
            action="college.assessment_scheme.assignment.upgrade", resource_type=existing.__tablename__,
            resource_id=existing.id, permission="college.academics.manage",
            changes={
                "scope_key": scope_key,
                "before_scheme_id": before_scheme_id,
                "scheme_id": scheme.id,
                "scheme_version": scheme.version_number,
            },
        )
        db.commit()
        return {
            "id": existing.id, "scheme_id": existing.scheme_id,
            "scope_key": existing.scope_key, "version": existing.version,
        }
    assignment = CollegeAssessmentSchemeAssignment(
        organization_id=user.organization_id,
        scheme_id=scheme.id,
        program_id=body.program_id,
        cohort_id=body.cohort_id,
        term_id=body.term_id,
        scope_key=scope_key,
    )
    db.add(assignment)
    try:
        db.flush()
        log_action(
            db, organization_id=user.organization_id, user_id=user.id,
            action="college.assessment_scheme.assign", resource_type=assignment.__tablename__,
            resource_id=assignment.id, permission="college.academics.manage",
            changes={"scheme_id": scheme.id, "scope_key": scope_key},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Another pattern already owns this exact override scope") from exc
    return {"id": assignment.id, "scheme_id": scheme.id, "scope_key": scope_key, "version": assignment.version}


@router.get("/assessment-schemes/effective")
def effective_assessment_scheme(
    domain: SchemeDomain,
    program_id: str | None = None,
    cohort_id: str | None = None,
    term_id: str | None = None,
    user: User = Depends(require_permissions("college.academics.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "academics")
    validate_college_filters(access, program_id=program_id, cohort_id=cohort_id)
    scheme, assignment = resolve_effective_scheme(
        db, user.organization_id, domain=domain,
        program_id=program_id, cohort_id=cohort_id, term_id=term_id,
    )
    if not scheme:
        return {"configured": False, "scheme": None, "assignment": None}
    scheme, components, _assignments = load_scheme_bundle(db, user.organization_id, scheme.id)
    return {
        "configured": True,
        "scheme": scheme_payload(scheme, components, []),
        "assignment": {"id": assignment.id, "scope_key": assignment.scope_key} if assignment else None,
    }


@router.get("/assessment-schemes/{scheme_id}/readiness-mappings")
def assessment_readiness_mappings(
    scheme_id: str,
    user: User = Depends(require_permissions("college.readiness.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    resolve_college_access(db, user, "readiness")
    load_scheme_bundle(db, user.organization_id, scheme_id)
    rows = list(db.scalars(select(CollegeAssessmentReadinessMapping).where(
        CollegeAssessmentReadinessMapping.organization_id == user.organization_id,
        CollegeAssessmentReadinessMapping.scheme_id == scheme_id,
    ).order_by(CollegeAssessmentReadinessMapping.metric_code)))
    return {"items": [_readiness_mapping_payload(row) for row in rows]}


@router.put("/assessment-schemes/{scheme_id}/readiness-mappings")
def save_assessment_readiness_mapping(
    scheme_id: str,
    body: ReadinessMappingBody,
    user: User = Depends(require_permissions("college.readiness.policy.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    _require_institution_configuration(resolve_college_access(db, user, "readiness"), "readiness mappings")
    scheme, components, _assignments = load_scheme_bundle(db, user.organization_id, scheme_id)
    metric_code = str(body.metric_code or "").strip().upper()
    if metric_code != "__CALCULATED__":
        component = next((item for item in components if item.code == metric_code), None)
        if not component:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Select a metric from this assessment pattern")
        if component.metric_type not in {"number", "percentage", "integer", "rank", "count"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only numeric metrics can influence readiness")

    row = db.scalar(select(CollegeAssessmentReadinessMapping).where(
        CollegeAssessmentReadinessMapping.organization_id == user.organization_id,
        CollegeAssessmentReadinessMapping.scheme_id == scheme.id,
        CollegeAssessmentReadinessMapping.metric_code == metric_code,
    ))
    before = _readiness_mapping_payload(row) if row else None
    if row:
        if body.version is None or body.version != row.version:
            raise HTTPException(status.HTTP_409_CONFLICT, "This readiness mapping changed. Refresh and try again")
        row.factor_key = body.factor_key
        row.is_active = body.is_active
        row.mapped_by_user_id = user.id
        row.version += 1
        action = "college.assessment_readiness_mapping.update"
    else:
        if body.version is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "This readiness mapping no longer exists. Refresh and try again")
        row = CollegeAssessmentReadinessMapping(
            organization_id=user.organization_id,
            scheme_id=scheme.id,
            metric_code=metric_code,
            factor_key=body.factor_key,
            is_active=body.is_active,
            mapped_by_user_id=user.id,
        )
        db.add(row)
        action = "college.assessment_readiness_mapping.create"
    try:
        db.flush()
        log_action(
            db,
            organization_id=user.organization_id,
            user_id=user.id,
            action=action,
            resource_type=row.__tablename__,
            resource_id=row.id,
            permission="college.readiness.manage",
            changes={
                "scheme_id": scheme.id,
                "scheme_code": scheme.code,
                "metric_code": metric_code,
                "factor_key": body.factor_key,
                "is_active": body.is_active,
                "before": before,
            },
        )
        db.commit()
        db.refresh(row)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This metric already has a readiness mapping") from exc
    return _readiness_mapping_payload(row)


@router.get("/exam-cycles/page")
def exam_cycles_page(
    domain: SchemeDomain | None = None,
    term_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(require_permissions("college.assessments.view")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "assessments")
    filters = {"domain": domain, "term_id": term_id}
    values = decode_cursor(cursor, scope="college.exam-cycles", organization_id=user.organization_id, filters=filters)
    statement = select(CollegeExamCycle).where(CollegeExamCycle.organization_id == user.organization_id)
    if domain:
        statement = statement.where(CollegeExamCycle.domain == domain)
    if term_id:
        statement = statement.where(CollegeExamCycle.term_id == term_id)
    if values:
        at = datetime.fromisoformat(str(values["at"]))
        statement = statement.where(or_(
            CollegeExamCycle.created_at < at,
            and_(CollegeExamCycle.created_at == at, CollegeExamCycle.id < str(values["id"])),
        ))
    size = page_size(limit)
    candidates = list(db.scalars(statement.order_by(
        CollegeExamCycle.created_at.desc(), CollegeExamCycle.id.desc(),
    ).limit(min(1000, max(size * 8, size + 1)))))
    rows = [row for row in candidates if (
        access.unrestricted
        or bool(set(row.target_offering_ids or []) & set(access.course_offering_ids))
        or bool(set(row.target_cohort_ids or []) & set(access.cohort_ids))
    )]
    has_more = len(rows) > size
    rows = rows[:size]
    items = [{
        "id": row.id, "name": row.name, "code": row.code, "domain": row.domain,
        "scheme_id": row.scheme_id, "scheme_component_id": row.scheme_component_id,
        "term_id": row.term_id, "held_on": row.held_on, "due_on": row.due_on,
        "status": row.status, "target_count": len(row.target_offering_ids or row.target_cohort_ids or []),
        "scheme_snapshot": row.scheme_snapshot, "version": row.version, "created_at": row.created_at,
    } for row in rows]
    next_cursor = encode_cursor(
        scope="college.exam-cycles", organization_id=user.organization_id, filters=filters,
        values={"at": rows[-1].created_at.isoformat(), "id": rows[-1].id},
    ) if has_more and rows else None
    return page_response(items, next_cursor)


@router.post("/exam-cycles", status_code=201)
def create_exam_cycle(
    body: ExamCycleBody,
    user: User = Depends(require_permissions("college.assessments.manage")),
    db: Session = Depends(get_db),
):
    require_college(db, user)
    access = resolve_college_access(db, user, "assessments")
    scheme, components, _assignments = load_scheme_bundle(db, user.organization_id, body.scheme_id)
    if scheme.status not in {"active", "frozen"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Activate this pattern before creating an exam cycle")
    component = next((item for item in components if item.id == body.scheme_component_id), None)
    if body.scheme_component_id and not component:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The selected component does not belong to this pattern")
    if scheme.domain == "academic" and not component:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Select the configured academic component for this exam cycle")
    if scheme.domain == "academic" and not body.offering_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Select at least one course offering")
    if scheme.domain != "academic" and not body.cohort_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Select at least one cohort")

    offerings = list(db.scalars(select(CollegeCourseOffering).where(
        CollegeCourseOffering.organization_id == user.organization_id,
        CollegeCourseOffering.id.in_(body.offering_ids),
    ))) if body.offering_ids else []
    if len(offerings) != len(body.offering_ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "One or more course offerings are outside this college")
    for offering in offerings:
        access.require_course_offering(offering.id)
    if body.term_id and any(item.term_id != body.term_id for item in offerings):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Every course offering must belong to the selected term")

    snapshot = build_scheme_snapshot(scheme, components)
    metric_definitions = [component_payload(component)] if component else snapshot["components"]
    cycle = CollegeExamCycle(
        organization_id=user.organization_id,
        scheme_id=scheme.id,
        scheme_component_id=component.id if component else None,
        term_id=body.term_id,
        name=body.name,
        code=normalize_code(body.code),
        domain=scheme.domain,
        held_on=body.held_on,
        due_on=body.due_on,
        target_offering_ids=body.offering_ids,
        target_cohort_ids=body.cohort_ids,
        scheme_snapshot=snapshot,
    )
    db.add(cycle)
    db.flush()
    assessments: list[CollegeAssessment] = []
    if scheme.domain == "academic":
        for offering in offerings:
            assessments.append(CollegeAssessment(
                organization_id=user.organization_id,
                offering_id=offering.id,
                cohort_id=offering.cohort_id,
                exam_cycle_id=cycle.id,
                scheme_id=scheme.id,
                scheme_component_id=component.id,
                title=body.name,
                assessment_type=component.component_type,
                max_marks=component.max_marks or scheme.final_score_max,
                weightage_bps=component.weightage_bps,
                due_on=body.due_on,
                metric_schema=metric_definitions,
            ))
    else:
        for cohort_id in body.cohort_ids:
            tenant_row(db, CollegeCohort, cohort_id, user, "Cohort")
            access.require_cohort(cohort_id)
            assessments.append(CollegeAssessment(
                organization_id=user.organization_id,
                cohort_id=cohort_id,
                exam_cycle_id=cycle.id,
                scheme_id=scheme.id,
                scheme_component_id=component.id if component else None,
                title=body.name,
                assessment_type=component.component_type if component else scheme.domain,
                max_marks=component.max_marks if component and component.max_marks else scheme.final_score_max,
                weightage_bps=component.weightage_bps if component else 10000,
                due_on=body.due_on,
                metric_schema=metric_definitions,
            ))
    db.add_all(assessments)
    freeze_scheme(scheme)
    try:
        db.flush()
        log_action(
            db, organization_id=user.organization_id, user_id=user.id,
            action="college.exam_cycle.create", resource_type=cycle.__tablename__, resource_id=cycle.id,
            permission="college.assessments.manage", rows_affected=len(assessments),
            changes={"scheme_id": scheme.id, "scheme_version": scheme.version_number},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An exam cycle with this code already exists") from exc
    return {
        "id": cycle.id,
        "name": cycle.name,
        "code": cycle.code,
        "domain": cycle.domain,
        "scheme_id": scheme.id,
        "scheme_version": scheme.version_number,
        "assessment_count": len(assessments),
        "status": cycle.status,
    }
