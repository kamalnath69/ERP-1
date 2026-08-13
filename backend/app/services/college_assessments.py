"""Institution-configured College assessment schemes and deterministic scoring."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CollegeAssessment,
    CollegeAssessmentComponent,
    CollegeAssessmentScheme,
    CollegeAssessmentSchemeAssignment,
    CollegeAssessmentScore,
    CollegeCohort,
    CollegeExamCycle,
    CollegeProgram,
    CollegeTerm,
)


SCHEME_DOMAINS = {"academic", "coding", "placement"}
METRIC_TYPES = {
    "number", "percentage", "integer", "boolean", "short_text", "grade", "rank", "count",
}
NUMERIC_METRIC_TYPES = {"number", "percentage", "integer", "rank", "count"}
CALCULATION_METHODS = {"weighted_sum", "average", "best_n"}
SCORING_SCALE = Decimal("0.01")


def normalize_code(value: str, *, max_length: int = 60) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", str(value or "").strip().upper()).strip("_")
    if not normalized:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A code is required")
    return normalized[:max_length]


def _decimal(value: Any, *, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be a finite number")
    return parsed


def component_payload(component: CollegeAssessmentComponent) -> dict:
    return {
        "id": component.id,
        "name": component.name,
        "code": component.code,
        "component_type": component.component_type,
        "metric_type": component.metric_type,
        "display_order": component.display_order,
        "max_marks": float(component.max_marks) if component.max_marks is not None else None,
        "weightage_bps": component.weightage_bps,
        "pass_marks": float(component.pass_marks) if component.pass_marks is not None else None,
        "is_required": component.is_required,
        "aggregation_group": component.aggregation_group,
        "settings": component.settings or {},
    }


def assignment_payload(assignment: CollegeAssessmentSchemeAssignment) -> dict:
    return {
        "id": assignment.id,
        "scheme_id": assignment.scheme_id,
        "program_id": assignment.program_id,
        "cohort_id": assignment.cohort_id,
        "term_id": assignment.term_id,
        "scope_key": assignment.scope_key,
        "is_active": assignment.is_active,
        "version": assignment.version,
    }


def scheme_payload(
    scheme: CollegeAssessmentScheme,
    components: Iterable[CollegeAssessmentComponent] = (),
    assignments: Iterable[CollegeAssessmentSchemeAssignment] = (),
) -> dict:
    return {
        "id": scheme.id,
        "name": scheme.name,
        "code": scheme.code,
        "domain": scheme.domain,
        "description": scheme.description,
        "version_number": scheme.version_number,
        "supersedes_scheme_id": scheme.supersedes_scheme_id,
        "status": scheme.status,
        "final_score_max": float(scheme.final_score_max),
        "calculation_method": scheme.calculation_method,
        "calculation_config": scheme.calculation_config or {},
        "frozen_at": scheme.frozen_at,
        "version": scheme.version,
        "created_at": scheme.created_at,
        "updated_at": scheme.updated_at,
        "components": [component_payload(item) for item in components],
        "assignments": [assignment_payload(item) for item in assignments],
    }


def load_scheme_bundle(db: Session, organization_id: str, scheme_id: str) -> tuple[
    CollegeAssessmentScheme, list[CollegeAssessmentComponent], list[CollegeAssessmentSchemeAssignment]
]:
    scheme = db.scalar(select(CollegeAssessmentScheme).where(
        CollegeAssessmentScheme.id == scheme_id,
        CollegeAssessmentScheme.organization_id == organization_id,
    ))
    if not scheme:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assessment pattern not found")
    components = list(db.scalars(select(CollegeAssessmentComponent).where(
        CollegeAssessmentComponent.organization_id == organization_id,
        CollegeAssessmentComponent.scheme_id == scheme.id,
    ).order_by(CollegeAssessmentComponent.display_order, CollegeAssessmentComponent.id)))
    assignments = list(db.scalars(select(CollegeAssessmentSchemeAssignment).where(
        CollegeAssessmentSchemeAssignment.organization_id == organization_id,
        CollegeAssessmentSchemeAssignment.scheme_id == scheme.id,
    ).order_by(CollegeAssessmentSchemeAssignment.created_at, CollegeAssessmentSchemeAssignment.id)))
    return scheme, components, assignments


def validate_component_definitions(components: list[dict], calculation_method: str, calculation_config: dict) -> list[dict]:
    if not components:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Add at least one assessment component")
    if len(components) > 100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A pattern can contain at most 100 components")
    if calculation_method not in CALCULATION_METHODS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported calculation method")

    normalized: list[dict] = []
    seen_codes: set[str] = set()
    seen_orders: set[int] = set()
    for index, raw in enumerate(components, start=1):
        code = normalize_code(raw.get("code") or raw.get("name") or "", max_length=50)
        name = " ".join(str(raw.get("name") or "").split())
        metric_type = str(raw.get("metric_type") or "number")
        display_order = int(raw.get("display_order") or index)
        if len(name) < 2 or len(name) > 140:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Component {index} needs a valid name")
        if code in seen_codes:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Component code {code} appears more than once")
        if display_order in seen_orders:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Component order values must be unique")
        if metric_type not in METRIC_TYPES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unsupported metric type for {name}")

        max_marks = raw.get("max_marks")
        pass_marks = raw.get("pass_marks")
        weightage_bps = int(raw.get("weightage_bps") or 0)
        if max_marks not in (None, ""):
            max_marks = _decimal(max_marks, field=f"{name} maximum")
            if max_marks <= 0 or max_marks > Decimal("1000000"):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{name} maximum must be greater than zero")
        else:
            max_marks = Decimal("100") if metric_type == "percentage" else None
        if metric_type in NUMERIC_METRIC_TYPES and max_marks is None and calculation_method in CALCULATION_METHODS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{name} needs a maximum value for calculation")
        if pass_marks not in (None, ""):
            pass_marks = _decimal(pass_marks, field=f"{name} pass threshold")
            if pass_marks < 0 or (max_marks is not None and pass_marks > max_marks):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{name} pass threshold exceeds its maximum")
        if weightage_bps < 0 or weightage_bps > 10000:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{name} weightage must be between 0 and 100%")

        normalized.append({
            "name": name,
            "code": code,
            "component_type": " ".join(str(raw.get("component_type") or "assessment").split())[:50],
            "metric_type": metric_type,
            "display_order": display_order,
            "max_marks": max_marks,
            "weightage_bps": weightage_bps,
            "pass_marks": pass_marks,
            "is_required": bool(raw.get("is_required", True)),
            "aggregation_group": (" ".join(str(raw.get("aggregation_group") or "").split())[:50] or None),
            "settings": dict(raw.get("settings") or {}),
        })
        seen_codes.add(code)
        seen_orders.add(display_order)

    numeric = [item for item in normalized if item["metric_type"] in NUMERIC_METRIC_TYPES]
    if not numeric:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A calculated pattern needs at least one numeric component")
    if calculation_method == "weighted_sum" and sum(item["weightage_bps"] for item in numeric) <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Weighted patterns need at least one positive weightage")
    if calculation_method == "best_n":
        best_n = int((calculation_config or {}).get("best_n") or 0)
        if best_n < 1 or best_n > len(numeric):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Best N must be between 1 and the number of numeric components")
    minimum = int((calculation_config or {}).get("minimum_components") or 0)
    if minimum < 0 or minimum > len(numeric):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Minimum components is outside the configured component count")
    return sorted(normalized, key=lambda item: item["display_order"])


def assignment_scope_key(
    domain: str,
    *,
    program_id: str | None = None,
    cohort_id: str | None = None,
    term_id: str | None = None,
) -> str:
    if domain not in SCHEME_DOMAINS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported assessment domain")
    if term_id and not (program_id or cohort_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A term override must also select a program or cohort")
    if cohort_id:
        return f"{domain}:cohort:{cohort_id}:term:{term_id or '*'}"
    if program_id:
        return f"{domain}:program:{program_id}:term:{term_id or '*'}"
    return f"{domain}:institution"


def validate_assignment_scope(
    db: Session,
    organization_id: str,
    *,
    program_id: str | None,
    cohort_id: str | None,
    term_id: str | None,
) -> None:
    program = None
    if program_id:
        program = db.scalar(select(CollegeProgram).where(
            CollegeProgram.id == program_id,
            CollegeProgram.organization_id == organization_id,
        ))
        if not program:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Program does not belong to this college")
    if cohort_id:
        cohort = db.scalar(select(CollegeCohort).where(
            CollegeCohort.id == cohort_id,
            CollegeCohort.organization_id == organization_id,
        ))
        if not cohort:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Cohort does not belong to this college")
        if program and cohort.program_id != program.id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The selected cohort does not belong to the selected program")
    if term_id and not db.scalar(select(CollegeTerm.id).where(
        CollegeTerm.id == term_id,
        CollegeTerm.organization_id == organization_id,
    )):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Term does not belong to this college")


def resolve_effective_scheme(
    db: Session,
    organization_id: str,
    *,
    domain: str,
    program_id: str | None = None,
    cohort_id: str | None = None,
    term_id: str | None = None,
) -> tuple[CollegeAssessmentScheme | None, CollegeAssessmentSchemeAssignment | None]:
    if cohort_id and not program_id:
        cohort = db.scalar(select(CollegeCohort).where(
            CollegeCohort.id == cohort_id,
            CollegeCohort.organization_id == organization_id,
        ))
        if not cohort:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Cohort does not belong to this college")
        program_id = cohort.program_id
    keys = []
    if cohort_id and term_id:
        keys.append(assignment_scope_key(domain, cohort_id=cohort_id, term_id=term_id))
    if program_id and term_id:
        keys.append(assignment_scope_key(domain, program_id=program_id, term_id=term_id))
    if cohort_id:
        keys.append(assignment_scope_key(domain, cohort_id=cohort_id))
    if program_id:
        keys.append(assignment_scope_key(domain, program_id=program_id))
    keys.append(assignment_scope_key(domain))

    assignments = list(db.scalars(select(CollegeAssessmentSchemeAssignment).where(
        CollegeAssessmentSchemeAssignment.organization_id == organization_id,
        CollegeAssessmentSchemeAssignment.is_active.is_(True),
        CollegeAssessmentSchemeAssignment.scope_key.in_(keys),
    )))
    by_key = {item.scope_key: item for item in assignments}
    for key in keys:
        assignment = by_key.get(key)
        if not assignment:
            continue
        scheme = db.scalar(select(CollegeAssessmentScheme).where(
            CollegeAssessmentScheme.id == assignment.scheme_id,
            CollegeAssessmentScheme.organization_id == organization_id,
            CollegeAssessmentScheme.domain == domain,
            CollegeAssessmentScheme.status.in_(("active", "frozen")),
        ))
        if scheme:
            return scheme, assignment
    return None, None


def ensure_scheme_mutable(db: Session, scheme: CollegeAssessmentScheme) -> None:
    used = db.scalar(select(func.count(CollegeExamCycle.id)).where(
        CollegeExamCycle.organization_id == scheme.organization_id,
        CollegeExamCycle.scheme_id == scheme.id,
    )) or 0
    if scheme.frozen_at or used:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This assessment pattern is already in use. Create a new version for future cycles.",
        )


def freeze_scheme(scheme: CollegeAssessmentScheme) -> None:
    if not scheme.frozen_at:
        scheme.frozen_at = datetime.now(timezone.utc)
    scheme.status = "frozen"


def build_scheme_snapshot(scheme: CollegeAssessmentScheme, components: Iterable[CollegeAssessmentComponent]) -> dict:
    return {
        "scheme_id": scheme.id,
        "scheme_code": scheme.code,
        "scheme_name": scheme.name,
        "scheme_version": scheme.version_number,
        "domain": scheme.domain,
        "final_score_max": float(scheme.final_score_max),
        "calculation_method": scheme.calculation_method,
        "calculation_config": scheme.calculation_config or {},
        "components": [component_payload(component) for component in components],
    }


def validate_metric_values(component_definitions: Iterable[dict], metrics: dict, *, allow_partial: bool = True) -> dict:
    definitions = {str(item["code"]): item for item in component_definitions}
    unknown = sorted(set(metrics) - set(definitions))
    if unknown:
        raise ValueError(f"Unknown metrics: {', '.join(unknown[:10])}")
    normalized: dict[str, Any] = {}
    for code, definition in definitions.items():
        raw = metrics.get(code)
        if raw in (None, ""):
            if definition.get("is_required") and not allow_partial:
                raise ValueError(f"{definition['name']} is required")
            continue
        metric_type = definition.get("metric_type")
        if metric_type in NUMERIC_METRIC_TYPES:
            value = _decimal(raw, field=str(definition.get("name") or code))
            if metric_type in {"integer", "rank", "count"} and value != value.to_integral_value():
                raise ValueError(f"{definition['name']} must be a whole number")
            if value < 0:
                raise ValueError(f"{definition['name']} cannot be negative")
            maximum = definition.get("max_marks")
            if maximum is not None and value > _decimal(maximum, field=f"{definition['name']} maximum"):
                raise ValueError(f"{definition['name']} cannot exceed {maximum}")
            normalized[code] = int(value) if metric_type in {"integer", "rank", "count"} else float(value)
        elif metric_type == "boolean":
            if isinstance(raw, bool):
                normalized[code] = raw
            elif str(raw).strip().casefold() in {"true", "yes", "1"}:
                normalized[code] = True
            elif str(raw).strip().casefold() in {"false", "no", "0"}:
                normalized[code] = False
            else:
                raise ValueError(f"{definition['name']} must be yes or no")
        else:
            value = " ".join(str(raw).split())
            if len(value) > 200:
                raise ValueError(f"{definition['name']} is too long")
            normalized[code] = value
    return normalized


def calculate_score(snapshot: dict, metrics: dict, *, allow_partial: bool = True) -> Decimal | None:
    definitions = list(snapshot.get("components") or [])
    normalized = validate_metric_values(definitions, metrics, allow_partial=allow_partial)
    numeric = []
    for definition in definitions:
        code = str(definition["code"])
        if definition.get("metric_type") not in NUMERIC_METRIC_TYPES or code not in normalized:
            continue
        maximum = _decimal(definition.get("max_marks"), field=f"{definition.get('name')} maximum")
        if maximum <= 0:
            continue
        ratio = _decimal(normalized[code], field=str(definition.get("name") or code)) / maximum
        numeric.append((definition, min(Decimal("1"), max(Decimal("0"), ratio))))
    if not numeric:
        return None

    config = dict(snapshot.get("calculation_config") or {})
    minimum = int(config.get("minimum_components") or 0)
    if len(numeric) < minimum:
        return None
    method = str(snapshot.get("calculation_method") or "weighted_sum")
    if method == "weighted_sum":
        weighted = [(item, Decimal(str(definition.get("weightage_bps") or 0))) for definition, item in numeric]
        total_weight = sum((weight for _item, weight in weighted), Decimal("0"))
        if total_weight <= 0:
            return None
        ratio = sum((item * weight for item, weight in weighted), Decimal("0")) / total_weight
    elif method == "average":
        ratio = sum((item for _definition, item in numeric), Decimal("0")) / Decimal(len(numeric))
    elif method == "best_n":
        best_n = int(config.get("best_n") or 0)
        if best_n < 1 or len(numeric) < best_n:
            return None
        selected = sorted((item for _definition, item in numeric), reverse=True)[:best_n]
        ratio = sum(selected, Decimal("0")) / Decimal(best_n)
    else:
        raise ValueError("Unsupported calculation method")
    scale = _decimal(snapshot.get("final_score_max") or 100, field="Final score scale")
    return (ratio * scale).quantize(SCORING_SCALE, rounding=ROUND_HALF_UP)


def recalculate_assessment_score(
    db: Session,
    assessment: CollegeAssessment,
    student_profile_id: str,
) -> Decimal | None:
    """Calculate one dynamic result, aggregating academic component cycles safely."""
    cycle = db.get(CollegeExamCycle, assessment.exam_cycle_id) if assessment.exam_cycle_id else None
    if not cycle:
        return None
    if not assessment.offering_id or not assessment.scheme_id:
        score = db.scalar(select(CollegeAssessmentScore).where(
            CollegeAssessmentScore.organization_id == assessment.organization_id,
            CollegeAssessmentScore.assessment_id == assessment.id,
            CollegeAssessmentScore.student_profile_id == student_profile_id,
        ))
        result = calculate_score(cycle.scheme_snapshot, dict(score.metrics or {}), allow_partial=True) if score else None
        if score:
            score.calculated_score = result
        return result

    rows = db.execute(
        select(CollegeAssessmentScore, CollegeAssessment)
        .join(CollegeAssessment, CollegeAssessment.id == CollegeAssessmentScore.assessment_id)
        .where(
            CollegeAssessmentScore.organization_id == assessment.organization_id,
            CollegeAssessmentScore.student_profile_id == student_profile_id,
            CollegeAssessment.organization_id == assessment.organization_id,
            CollegeAssessment.scheme_id == assessment.scheme_id,
            CollegeAssessment.offering_id == assessment.offering_id,
        )
        .order_by(CollegeAssessment.created_at, CollegeAssessment.id)
    ).all()
    combined_metrics: dict[str, Any] = {}
    scores: list[CollegeAssessmentScore] = []
    for score, _row_assessment in rows:
        combined_metrics.update(score.metrics or {})
        scores.append(score)
    result = calculate_score(cycle.scheme_snapshot, combined_metrics, allow_partial=True)
    for score in scores:
        score.calculated_score = result
    return result
