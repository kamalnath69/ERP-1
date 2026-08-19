"""Governed qualitative definitions; values are data, never executable code."""
from __future__ import annotations

from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AISemanticPolicy


DEFAULT_DEFINITIONS = {
    "low_attendance_percent": 75.0,
    "severe_attendance_percent": 60.0,
    "consistent_attendance_percent": 90.0,
    "consistent_attendance_periods": 3,
    "sudden_attendance_drop_points": 10.0,
    "high_cgpa": 8.0,
    "subject_weak_percent": 50.0,
    "improvement_periods": 2,
    "overall_good_student_metric": "placement_readiness",
    "minimum_association_sample": 20,
}

NUMERIC_LIMITS = {
    "low_attendance_percent": (0.0, 100.0),
    "severe_attendance_percent": (0.0, 100.0),
    "consistent_attendance_percent": (0.0, 100.0),
    "consistent_attendance_periods": (2, 12),
    "sudden_attendance_drop_points": (0.0, 100.0),
    "high_cgpa": (0.0, 10.0),
    "subject_weak_percent": (0.0, 100.0),
    "improvement_periods": (2, 12),
    "minimum_association_sample": (10, 10000),
}


def validate_definitions(values: dict) -> dict:
    unknown = set(values) - set(DEFAULT_DEFINITIONS)
    if unknown:
        raise ValueError(f"Unknown assistant definitions: {', '.join(sorted(unknown))}")
    result = deepcopy(DEFAULT_DEFINITIONS)
    result.update(values)
    if result["overall_good_student_metric"] != "placement_readiness":
        raise ValueError("Overall-good-student must use the reviewed placement-readiness policy")
    for key, (minimum, maximum) in NUMERIC_LIMITS.items():
        value = result[key]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not minimum <= value <= maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}")
    if result["severe_attendance_percent"] > result["low_attendance_percent"]:
        raise ValueError("Severe attendance must not exceed the low-attendance threshold")
    return result


def semantic_definitions(db: Session, organization_id: str) -> dict:
    row = db.execute(select(AISemanticPolicy).where(
        AISemanticPolicy.organization_id == organization_id,
    )).scalar_one_or_none()
    return validate_definitions(dict(row.definitions or {})) if row else deepcopy(DEFAULT_DEFINITIONS)
