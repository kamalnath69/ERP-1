"""Evidence-backed College placement readiness and dashboard services."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Client, CollegeAssessment, CollegeAssessmentComponent, CollegeAssessmentReadinessMapping,
    CollegeAssessmentScheme, CollegeAssessmentScore, CollegeAttendanceRecord,
    CollegeAttendanceSession, CollegeAttendanceSnapshot, CollegeCareerEvidence,
    CollegeCareerProfile, CollegeCodingSnapshot, CollegeCohort, CollegeCourseOffering,
    CollegeCodingAccount, CollegeClearanceSnapshot, CollegeDepartment, CollegePipelineStage, CollegePlacementApplication,
    CollegePlacementAssessment, CollegePlacementCompany, CollegePlacementOffer,
    CollegePlacementInterview, CollegePlacementOpportunity, CollegePreparationActivity, CollegeProgram,
    CollegeReadinessPolicy, CollegeReadinessSnapshot, CollegeStudentProfile,
    CollegeApplicationStageEvent, CollegeStudentFee, CollegeStudentIntervention, CollegeTerm,
    CollegeTermResult, SaleInvoice,
)
from app.services.college_access import opportunity_rules_match_scope


DEFAULT_WEIGHTS = {
    "academics": 25,
    "coding": 25,
    "assessment": 20,
    "profile": 15,
    "attendance": 10,
    "training": 5,
}
DEFAULT_BANDS = {"ready": 75, "developing": 50}
DEFAULT_PIPELINE = (
    ("Eligible", "eligible", "active"),
    ("Invited", "invited", "active"),
    ("Applied", "applied", "active"),
    ("Assessment", "assessment", "active"),
    ("Technical Interview", "technical-interview", "active"),
    ("HR Interview", "hr-interview", "active"),
    ("Selected", "selected", "active"),
    ("Offered", "offered", "active"),
    ("Joined", "joined", "placed"),
    ("Rejected", "rejected", "rejected"),
    ("Withdrawn", "withdrawn", "withdrawn"),
)


def _float(value) -> float | None:
    return float(value) if value is not None else None


def _round(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _clamp(value: float) -> float:
    return min(100.0, max(0.0, value))


def ensure_default_pipeline(db: Session, organization_id: str) -> list[CollegePipelineStage]:
    rows = list(db.execute(
        select(CollegePipelineStage)
        .where(CollegePipelineStage.organization_id == organization_id)
        .order_by(CollegePipelineStage.display_order)
    ).scalars())
    if rows:
        return rows
    for order, (name, slug, stage_type) in enumerate(DEFAULT_PIPELINE, start=1):
        db.add(CollegePipelineStage(
            organization_id=organization_id,
            name=name,
            slug=slug,
            display_order=order,
            stage_type=stage_type,
            is_terminal=stage_type != "active",
            is_enabled=True,
        ))
    db.flush()
    return list(db.execute(
        select(CollegePipelineStage)
        .where(CollegePipelineStage.organization_id == organization_id)
        .order_by(CollegePipelineStage.display_order)
    ).scalars())


def active_readiness_policy(
    db: Session,
    organization_id: str,
    *,
    created_by_user_id: str | None = None,
) -> CollegeReadinessPolicy:
    policy = db.execute(
        select(CollegeReadinessPolicy)
        .where(
            CollegeReadinessPolicy.organization_id == organization_id,
            CollegeReadinessPolicy.is_active.is_(True),
        )
        .order_by(CollegeReadinessPolicy.version.desc())
    ).scalars().first()
    if policy:
        return policy
    policy = CollegeReadinessPolicy(
        organization_id=organization_id,
        name="Placement readiness",
        version=1,
        weights=DEFAULT_WEIGHTS,
        bands=DEFAULT_BANDS,
        minimum_coverage_percent=Decimal("60.00"),
        is_active=True,
        created_by_user_id=created_by_user_id,
    )
    db.add(policy)
    db.flush()
    return policy


def student_query(
    organization_id: str,
    *,
    academic_year: str | None = None,
    graduation_year: int | None = None,
    department_id: str | None = None,
    program_id: str | None = None,
    cohort_id: str | None = None,
    cohort_ids: list[str] | set[str] | None = None,
    allowed_student_ids: set[str] | None = None,
):
    query = (
        select(CollegeStudentProfile)
        .join(CollegeProgram, CollegeProgram.id == CollegeStudentProfile.program_id)
        .join(CollegeCohort, CollegeCohort.id == CollegeStudentProfile.cohort_id)
        .where(
            CollegeStudentProfile.organization_id == organization_id,
            CollegeStudentProfile.status == "active",
        )
    )
    if academic_year:
        start_year = int(academic_year[:4]) if academic_year[:4].isdigit() else None
        if start_year:
            query = query.where(CollegeCohort.admission_year <= start_year)
    if graduation_year:
        query = query.where(CollegeCohort.graduation_year == graduation_year)
    if department_id:
        query = query.where(CollegeProgram.department_id == department_id)
    if program_id:
        query = query.where(CollegeStudentProfile.program_id == program_id)
    if cohort_id:
        query = query.where(CollegeStudentProfile.cohort_id == cohort_id)
    if cohort_ids:
        query = query.where(CollegeStudentProfile.cohort_id.in_(set(cohort_ids)))
    if allowed_student_ids is not None:
        query = query.where(CollegeStudentProfile.id.in_(allowed_student_ids))
    return query.order_by(CollegeStudentProfile.admission_number)


def _first_by_student(rows: Iterable, key="student_profile_id") -> dict[str, object]:
    result = {}
    for row in rows:
        student_id = getattr(row, key)
        result.setdefault(student_id, row)
    return result


def _attendance_from_sessions(db: Session, organization_id: str, student_ids: list[str]) -> dict[str, dict]:
    if not student_ids:
        return {}
    rows = db.execute(
        select(
            CollegeAttendanceRecord.student_profile_id,
            func.count(CollegeAttendanceRecord.id),
            func.sum(case((CollegeAttendanceRecord.status.in_(("present", "late")), 1), else_=0)),
        )
        .join(CollegeAttendanceSession, CollegeAttendanceSession.id == CollegeAttendanceRecord.session_id)
        .where(
            CollegeAttendanceRecord.organization_id == organization_id,
            CollegeAttendanceRecord.student_profile_id.in_(student_ids),
            CollegeAttendanceSession.status == "published",
        )
        .group_by(CollegeAttendanceRecord.student_profile_id)
    ).all()
    return {
        student_id: {
            "value": _clamp((attended or 0) * 100 / total) if total else None,
            "source_ids": [],
            "source": "attendance_records",
        }
        for student_id, total, attended in rows
    }


def _mapped_assessment_evidence(
    db: Session,
    organization_id: str,
    student_ids: list[str],
) -> dict[str, dict[str, dict]]:
    """Normalize only assessment metrics explicitly authorized for readiness."""
    mappings = list(db.scalars(select(CollegeAssessmentReadinessMapping).where(
        CollegeAssessmentReadinessMapping.organization_id == organization_id,
        CollegeAssessmentReadinessMapping.is_active.is_(True),
    )))
    if not mappings:
        return {}
    scheme_ids = {row.scheme_id for row in mappings}
    mappings_by_scheme: dict[str, list[CollegeAssessmentReadinessMapping]] = defaultdict(list)
    for row in mappings:
        mappings_by_scheme[row.scheme_id].append(row)
    components = {
        (row.scheme_id, row.code): row
        for row in db.scalars(select(CollegeAssessmentComponent).where(
            CollegeAssessmentComponent.organization_id == organization_id,
            CollegeAssessmentComponent.scheme_id.in_(scheme_ids),
        ))
    }
    score_rows = db.execute(
        select(CollegeAssessmentScore, CollegeAssessment, CollegeAssessmentScheme)
        .join(CollegeAssessment, CollegeAssessment.id == CollegeAssessmentScore.assessment_id)
        .join(CollegeAssessmentScheme, CollegeAssessmentScheme.id == CollegeAssessment.scheme_id)
        .where(
            CollegeAssessmentScore.organization_id == organization_id,
            CollegeAssessmentScore.student_profile_id.in_(student_ids),
            CollegeAssessment.scheme_id.in_(scheme_ids),
            CollegeAssessment.status == "published",
        )
        .order_by(CollegeAssessmentScore.updated_at.desc(), CollegeAssessmentScore.id.desc())
    ).all()

    # Keep the latest observation for each student, pattern, and mapped metric. A
    # repeated exam cycle should update evidence, not silently multiply its weight.
    latest: dict[tuple[str, str, str, str], tuple[float, str, str]] = {}
    for score, assessment, scheme in score_rows:
        for mapping in mappings_by_scheme.get(scheme.id, []):
            evidence_scope = assessment.offering_id or "cohort"
            key = (score.student_profile_id, scheme.id, mapping.metric_code, evidence_scope)
            if key in latest:
                continue
            if mapping.metric_code == "__CALCULATED__":
                if score.calculated_score is None or not scheme.final_score_max:
                    continue
                value = _clamp(float(score.calculated_score) * 100 / float(scheme.final_score_max))
            else:
                component = components.get((scheme.id, mapping.metric_code))
                raw = (score.metrics or {}).get(mapping.metric_code)
                if not component or raw is None or component.max_marks is None:
                    continue
                maximum = float(component.max_marks)
                if maximum <= 0:
                    continue
                numeric = float(raw)
                if component.metric_type == "rank":
                    value = 100 if maximum <= 1 else _clamp((maximum - numeric) * 100 / (maximum - 1))
                else:
                    value = _clamp(numeric * 100 / maximum)
            latest[key] = (value, score.id, mapping.factor_key)

    grouped: dict[str, dict[str, dict[str, list]]] = defaultdict(
        lambda: defaultdict(lambda: {"values": [], "source_ids": []})
    )
    for (student_id, _scheme_id, _metric_code, _scope), (value, score_id, factor_key) in latest.items():
        grouped[student_id][factor_key]["values"].append(value)
        grouped[student_id][factor_key]["source_ids"].append(score_id)
    return {
        student_id: {
            factor_key: {
                "value": sum(data["values"]) / len(data["values"]),
                "source_ids": data["source_ids"],
                "source": "mapped_assessment_metrics",
            }
            for factor_key, data in factors.items()
        }
        for student_id, factors in grouped.items()
    }


def _merge_readiness_evidence(base: dict, mapped: dict | None) -> dict:
    if not mapped or mapped.get("value") is None:
        return base
    if base.get("value") is None:
        return mapped
    return {
        "value": (float(base["value"]) + float(mapped["value"])) / 2,
        "source_ids": list(base.get("source_ids") or []) + list(mapped.get("source_ids") or []),
        "source": "combined",
    }


def evidence_context(db: Session, organization_id: str, student_ids: list[str]) -> dict[str, dict]:
    """Load all readiness evidence in bounded queries for a student set."""
    if not student_ids:
        return {}
    term_results = list(db.execute(
        select(CollegeTermResult)
        .where(
            CollegeTermResult.organization_id == organization_id,
            CollegeTermResult.student_profile_id.in_(student_ids),
        )
        .order_by(CollegeTermResult.student_profile_id, CollegeTermResult.semester.desc(), CollegeTermResult.created_at.desc())
    ).scalars())
    attendance_snapshots = list(db.execute(
        select(CollegeAttendanceSnapshot)
        .where(
            CollegeAttendanceSnapshot.organization_id == organization_id,
            CollegeAttendanceSnapshot.student_profile_id.in_(student_ids),
            CollegeAttendanceSnapshot.course_id.is_(None),
        )
        .order_by(CollegeAttendanceSnapshot.student_profile_id, CollegeAttendanceSnapshot.as_of.desc())
    ).scalars())
    placement_assessments = list(db.execute(
        select(CollegePlacementAssessment)
        .where(
            CollegePlacementAssessment.organization_id == organization_id,
            CollegePlacementAssessment.student_profile_id.in_(student_ids),
            CollegePlacementAssessment.score_percent.is_not(None),
        )
        .order_by(CollegePlacementAssessment.student_profile_id, CollegePlacementAssessment.assessed_on.desc().nullslast())
    ).scalars())
    career_profiles = {
        row.student_profile_id: row for row in db.execute(
            select(CollegeCareerProfile).where(
                CollegeCareerProfile.organization_id == organization_id,
                CollegeCareerProfile.student_profile_id.in_(student_ids),
            )
        ).scalars()
    }
    evidence_rows = list(db.execute(
        select(CollegeCareerEvidence).where(
            CollegeCareerEvidence.organization_id == organization_id,
            CollegeCareerEvidence.student_profile_id.in_(student_ids),
        )
    ).scalars())
    coding_rows = list(db.execute(
        select(CollegeCodingSnapshot)
        .where(
            CollegeCodingSnapshot.organization_id == organization_id,
            CollegeCodingSnapshot.student_profile_id.in_(student_ids),
        )
        .order_by(CollegeCodingSnapshot.student_profile_id, CollegeCodingSnapshot.captured_at.desc())
    ).scalars())
    preparation_rows = list(db.execute(
        select(CollegePreparationActivity).where(
            CollegePreparationActivity.organization_id == organization_id,
            CollegePreparationActivity.student_profile_id.in_(student_ids),
            CollegePreparationActivity.status == "completed",
        )
    ).scalars())

    results_by_student = _first_by_student(term_results)
    snapshots_by_student = _first_by_student(attendance_snapshots)
    assessment_groups = defaultdict(list)
    for row in placement_assessments:
        assessment_groups[row.student_profile_id].append(row)
    evidence_groups = defaultdict(list)
    for row in evidence_rows:
        evidence_groups[row.student_profile_id].append(row)
    coding_by_student = _first_by_student(coding_rows)
    prep_groups = defaultdict(list)
    for row in preparation_rows:
        prep_groups[row.student_profile_id].append(row)
    session_attendance = _attendance_from_sessions(db, organization_id, student_ids)
    mapped_assessments = _mapped_assessment_evidence(db, organization_id, student_ids)

    context = {}
    for student_id in student_ids:
        result = results_by_student.get(student_id)
        academic_value = None
        academic_sources = []
        if result and result.cgpa is not None:
            backlog_penalty = min(25, (result.active_backlogs or 0) * 5)
            academic_value = _clamp(float(result.cgpa) * 10 - backlog_penalty)
            academic_sources = [result.id]

        snapshot = snapshots_by_student.get(student_id)
        if snapshot and snapshot.attendance_percent is not None:
            attendance = {
                "value": _clamp(float(snapshot.attendance_percent)),
                "source_ids": [snapshot.id],
                "source": "attendance_snapshot",
            }
        else:
            attendance = session_attendance.get(student_id, {"value": None, "source_ids": [], "source": None})

        assessment_rows = assessment_groups[student_id]
        scored_assessments = [float(row.score_percent) for row in assessment_rows if row.score_percent is not None]
        assessment_value = sum(scored_assessments) / len(scored_assessments) if scored_assessments else None

        coding = coding_by_student.get(student_id)
        coding_value = None
        if coding:
            difficulty_points = (
                (coding.easy_solved or 0)
                + 2 * (coding.medium_solved or 0)
                + 3 * (coding.hard_solved or 0)
            )
            solved_score = _clamp(difficulty_points / 4)
            if coding.contest_rating is not None:
                rating_score = _clamp((float(coding.contest_rating) - 1200) / 12)
                coding_value = solved_score * 0.7 + rating_score * 0.3
            else:
                coding_value = solved_score

        profile = career_profiles.get(student_id)
        evidence = evidence_groups[student_id]
        verified = [row for row in evidence if row.is_verified]
        type_counts = Counter(row.evidence_type for row in verified)
        profile_has_evidence = bool(profile and profile.resume_status != "missing") or bool(evidence)
        profile_value = None
        if profile_has_evidence:
            resume_points = 35 if profile and profile.resume_status in {"reviewed", "approved"} else 15 if profile and profile.resume_status != "missing" else 0
            skill_points = min(30, type_counts["skill"] * 6)
            project_points = min(25, type_counts["project"] * 12.5)
            certification_points = min(10, type_counts["certification"] * 5)
            profile_value = resume_points + skill_points + project_points + certification_points

        preparations = prep_groups[student_id]
        training_value = None
        if preparations:
            outcomes = [float(row.outcome_score) for row in preparations if row.outcome_score is not None]
            completion_score = min(100, len(preparations) * 20)
            training_value = completion_score if not outcomes else completion_score * 0.5 + (sum(outcomes) / len(outcomes)) * 0.5

        base_factors = {
            "academics": {"value": academic_value, "source_ids": academic_sources},
            "coding": {"value": coding_value, "source_ids": [coding.id] if coding else []},
            "assessment": {"value": assessment_value, "source_ids": [row.id for row in assessment_rows]},
            "profile": {"value": profile_value, "source_ids": [row.id for row in evidence] + ([profile.id] if profile else [])},
            "attendance": attendance,
            "training": {"value": training_value, "source_ids": [row.id for row in preparations]},
        }
        mapped_factors = mapped_assessments.get(student_id, {})
        context[student_id] = {
            key: _merge_readiness_evidence(value, mapped_factors.get(key))
            for key, value in base_factors.items()
        }
    return context


def calculate_readiness(evidence: dict, policy: CollegeReadinessPolicy) -> dict:
    weights = {**DEFAULT_WEIGHTS, **(policy.weights or {})}
    total_weight = sum(max(0, float(value)) for value in weights.values()) or 100
    known_weight = 0.0
    weighted_score = 0.0
    factors = {}
    missing = []
    sources = {}
    for key, weight_value in weights.items():
        weight = max(0.0, float(weight_value))
        item = evidence.get(key) or {}
        value = item.get("value")
        source_ids = list(item.get("source_ids") or [])
        factors[key] = {
            "value": round(float(value), 2) if value is not None else None,
            "weight": weight,
            "available": value is not None,
        }
        sources[key] = source_ids
        if value is None:
            missing.append(key)
            continue
        known_weight += weight
        weighted_score += _clamp(float(value)) * weight
    score = weighted_score / known_weight if known_weight else None
    coverage = known_weight * 100 / total_weight
    bands = {**DEFAULT_BANDS, **(policy.bands or {})}
    if score is None:
        band = "insufficient_evidence"
    elif score >= float(bands["ready"]):
        band = "ready"
    elif score >= float(bands["developing"]):
        band = "developing"
    else:
        band = "needs_support"
    return {
        "score": round(score, 2) if score is not None else None,
        "coverage_percent": round(coverage, 2),
        "band": band,
        "rankable": score is not None and coverage >= float(policy.minimum_coverage_percent),
        "factors": factors,
        "missing_evidence": missing,
        "source_records": sources,
        "policy_version": policy.version,
    }


def recompute_readiness(
    db: Session,
    organization_id: str,
    student_ids: list[str] | None = None,
    *,
    created_by_user_id: str | None = None,
    calculated_at: datetime | None = None,
) -> list[CollegeReadinessSnapshot]:
    if student_ids is None:
        student_ids = list(db.execute(
            select(CollegeStudentProfile.id).where(
                CollegeStudentProfile.organization_id == organization_id,
                CollegeStudentProfile.status == "active",
            )
        ).scalars())
    policy = active_readiness_policy(db, organization_id, created_by_user_id=created_by_user_id)
    context = evidence_context(db, organization_id, student_ids)
    now = calculated_at or datetime.now(timezone.utc)
    snapshots = []
    for student_id in student_ids:
        result = calculate_readiness(context.get(student_id, {}), policy)
        row = CollegeReadinessSnapshot(
            organization_id=organization_id,
            student_profile_id=student_id,
            policy_id=policy.id,
            policy_version=policy.version,
            score=_round(result["score"]) if result["score"] is not None else None,
            coverage_percent=_round(result["coverage_percent"]),
            band=result["band"],
            factors=result["factors"],
            missing_evidence=result["missing_evidence"],
            source_records=result["source_records"],
            calculated_at=now,
        )
        db.add(row)
        snapshots.append(row)
    db.flush()
    return snapshots


def latest_readiness(db: Session, organization_id: str, student_ids: list[str]) -> dict[str, CollegeReadinessSnapshot]:
    if not student_ids:
        return {}
    rows = db.execute(
        select(CollegeReadinessSnapshot)
        .where(
            CollegeReadinessSnapshot.organization_id == organization_id,
            CollegeReadinessSnapshot.student_profile_id.in_(student_ids),
        )
        .order_by(CollegeReadinessSnapshot.student_profile_id, CollegeReadinessSnapshot.calculated_at.desc())
    ).scalars()
    return _first_by_student(rows)


def fee_clearance_by_student(
    db: Session,
    organization_id: str,
    student_ids: Iterable[str],
) -> dict[str, dict]:
    """Summarize authoritative College fee obligations without mixing in other sales."""
    ids = list(dict.fromkeys(student_ids))
    summaries = {
        student_id: {
            "status": "needs_review",
            "assigned_count": 0,
            "cleared_count": 0,
            "open_invoice_count": 0,
            "outstanding_paise": 0,
            "fee_record_ids": [],
            "invoice_ids": [],
            "source_type": None,
            "source_updated_at": None,
            "is_stale": False,
        }
        for student_id in ids
    }
    if not ids:
        return summaries

    rows = db.execute(
        select(CollegeStudentFee, SaleInvoice)
        .outerjoin(SaleInvoice, SaleInvoice.id == CollegeStudentFee.invoice_id)
        .where(
            CollegeStudentFee.organization_id == organization_id,
            CollegeStudentFee.student_profile_id.in_(ids),
        )
    ).all()
    for fee, invoice in rows:
        summary = summaries[fee.student_profile_id]
        # A void/refunded invoice no longer proves that the related obligation is settled.
        if invoice and invoice.status in {"void", "refunded"}:
            continue
        summary["assigned_count"] += 1
        summary["fee_record_ids"].append(fee.id)
        if invoice:
            summary["invoice_ids"].append(invoice.id)
        outstanding = (
            max(0, int(invoice.total_paise) - int(invoice.paid_paise))
            if invoice
            else max(0, int(fee.amount_paise) - int(fee.concession_paise))
        )
        if fee.status == "waived" or outstanding == 0:
            summary["cleared_count"] += 1
            continue
        summary["outstanding_paise"] += outstanding
        if invoice:
            summary["open_invoice_count"] += 1

    for summary in summaries.values():
        if summary["assigned_count"] == 0:
            summary["status"] = "needs_review"
        elif summary["outstanding_paise"] > 0:
            summary["status"] = "pending"
        elif summary["cleared_count"] == summary["assigned_count"]:
            summary["status"] = "cleared"
        else:
            summary["status"] = "needs_review"
        if summary["assigned_count"]:
            summary["source_type"] = "local_fees"

    imported = db.execute(
        select(CollegeClearanceSnapshot)
        .where(
            CollegeClearanceSnapshot.organization_id == organization_id,
            CollegeClearanceSnapshot.student_profile_id.in_(ids),
        )
        .order_by(
            CollegeClearanceSnapshot.student_profile_id,
            CollegeClearanceSnapshot.source_updated_at.desc(),
            CollegeClearanceSnapshot.id.desc(),
        )
    ).scalars()
    latest_imported = _first_by_student(imported)
    stale_before = datetime.now(timezone.utc) - timedelta(days=7)
    for student_id, snapshot in latest_imported.items():
        is_stale = snapshot.source_updated_at < stale_before
        summaries[student_id] = {
            "status": "needs_review" if is_stale else snapshot.status,
            "assigned_count": 0,
            "cleared_count": 0,
            "open_invoice_count": 0,
            "outstanding_paise": 0,
            "fee_record_ids": [],
            "invoice_ids": [],
            "source_type": snapshot.source_type,
            "source_updated_at": snapshot.source_updated_at,
            "as_of": snapshot.as_of,
            "source_record_id": snapshot.id,
            "is_stale": is_stale,
        }
    return summaries


def opportunity_eligibility_rules(opportunity: CollegePlacementOpportunity) -> dict:
    """Internships always require fee clearance, including for legacy opportunities."""
    rules = dict(opportunity.eligibility_rules or {})
    if opportunity.opportunity_type == "internship":
        rules["require_fee_clearance"] = True
    return rules


def evaluate_eligibility(evidence: dict, rules: dict) -> dict:
    """Return tri-state eligibility with evidence; protected attributes are never accepted."""
    checks = []

    def add_check(name: str, actual, expected, passes: bool | None):
        checks.append({"rule": name, "actual": actual, "expected": expected, "passes": passes})

    term = evidence.get("term_result")
    attendance = evidence.get("attendance_percent")
    coding = evidence.get("coding")
    skills = {value.lower() for value in evidence.get("skills", [])}
    if rules.get("minimum_cgpa") is not None:
        actual = _float(term.cgpa) if term else None
        add_check("minimum_cgpa", actual, rules["minimum_cgpa"], None if actual is None else actual >= float(rules["minimum_cgpa"]))
    if rules.get("maximum_active_backlogs") is not None:
        actual = term.active_backlogs if term else None
        add_check("maximum_active_backlogs", actual, rules["maximum_active_backlogs"], None if actual is None else actual <= int(rules["maximum_active_backlogs"]))
    if rules.get("minimum_attendance") is not None:
        add_check("minimum_attendance", attendance, rules["minimum_attendance"], None if attendance is None else attendance >= float(rules["minimum_attendance"]))
    if rules.get("minimum_solved") is not None:
        actual = coding.total_solved if coding else None
        add_check("minimum_solved", actual, rules["minimum_solved"], None if actual is None else actual >= int(rules["minimum_solved"]))
    required_skills = {str(value).lower() for value in rules.get("required_skills", [])}
    if required_skills:
        add_check("required_skills", sorted(skills), sorted(required_skills), required_skills.issubset(skills) if skills else None)
    if rules.get("require_fee_clearance"):
        clearance = evidence.get("fee_clearance") or {}
        actual = clearance.get("status")
        passes = True if actual == "cleared" else False if actual == "pending" else None
        add_check("fee_clearance", actual, "cleared", passes)
    program_ids = set(rules.get("program_ids", []))
    if program_ids:
        actual = evidence.get("program_id")
        add_check("program_ids", actual, sorted(program_ids), actual in program_ids if actual else None)
    department_ids = set(rules.get("department_ids", []))
    if department_ids:
        actual = evidence.get("department_id")
        add_check("department_ids", actual, sorted(department_ids), actual in department_ids if actual else None)
    cohort_ids = set(rules.get("cohort_ids", [])) | set(rules.get("batch_ids", []))
    if cohort_ids:
        actual = evidence.get("cohort_id")
        add_check("cohort_ids", actual, sorted(cohort_ids), actual in cohort_ids if actual else None)
    graduation_years = {int(value) for value in rules.get("graduation_years", [])}
    if graduation_years:
        actual = evidence.get("graduation_year")
        add_check("graduation_years", actual, sorted(graduation_years), actual in graduation_years if actual else None)

    if any(item["passes"] is False for item in checks):
        status = "ineligible"
    elif any(item["passes"] is None for item in checks):
        status = "needs_review"
    else:
        status = "eligible"
    return {"status": status, "checks": checks, "evaluated_at": datetime.now(timezone.utc).isoformat()}


def eligibility_context(
    db: Session,
    organization_id: str,
    student_id: str,
    *,
    fee_clearance_evidence: dict | None = None,
) -> dict:
    student = db.execute(select(CollegeStudentProfile).where(
        CollegeStudentProfile.id == student_id,
        CollegeStudentProfile.organization_id == organization_id,
    )).scalar_one_or_none()
    if not student:
        return {}
    program = db.get(CollegeProgram, student.program_id)
    cohort = db.get(CollegeCohort, student.cohort_id)
    career = db.execute(select(CollegeCareerProfile).where(
        CollegeCareerProfile.organization_id == organization_id,
        CollegeCareerProfile.student_profile_id == student_id,
    )).scalar_one_or_none()
    term = db.execute(
        select(CollegeTermResult)
        .where(CollegeTermResult.organization_id == organization_id, CollegeTermResult.student_profile_id == student_id)
        .order_by(CollegeTermResult.semester.desc(), CollegeTermResult.created_at.desc())
    ).scalars().first()
    attendance = db.execute(
        select(CollegeAttendanceSnapshot)
        .where(
            CollegeAttendanceSnapshot.organization_id == organization_id,
            CollegeAttendanceSnapshot.student_profile_id == student_id,
            CollegeAttendanceSnapshot.course_id.is_(None),
        )
        .order_by(CollegeAttendanceSnapshot.as_of.desc())
    ).scalars().first()
    coding = db.execute(
        select(CollegeCodingSnapshot)
        .where(CollegeCodingSnapshot.organization_id == organization_id, CollegeCodingSnapshot.student_profile_id == student_id)
        .order_by(CollegeCodingSnapshot.captured_at.desc())
    ).scalars().first()
    skills = list(db.execute(select(CollegeCareerEvidence.title).where(
        CollegeCareerEvidence.organization_id == organization_id,
        CollegeCareerEvidence.student_profile_id == student_id,
        CollegeCareerEvidence.evidence_type == "skill",
        CollegeCareerEvidence.is_verified.is_(True),
    )).scalars())
    fee_clearance = fee_clearance_evidence or fee_clearance_by_student(
        db,
        organization_id,
        [student_id],
    )[student_id]
    return {
        "student_id": student.id,
        "program_id": student.program_id,
        "cohort_id": student.cohort_id,
        "department_id": program.department_id if program else None,
        "graduation_year": cohort.graduation_year if cohort else (career.graduation_year if career else None),
        "term_result": term,
        "attendance_percent": _float(attendance.attendance_percent) if attendance else None,
        "coding": coding,
        "skills": skills,
        "fee_clearance": fee_clearance,
    }


def placement_dashboard(
    db: Session,
    organization_id: str,
    *,
    academic_year: str | None = None,
    graduation_year: int | None = None,
    department_id: str | None = None,
    program_id: str | None = None,
    cohort_id: str | None = None,
    cohort_ids: list[str] | set[str] | None = None,
    allowed_student_ids: set[str] | None = None,
) -> dict:
    students = list(db.execute(student_query(
        organization_id,
        academic_year=academic_year,
        graduation_year=graduation_year,
        department_id=department_id,
        program_id=program_id,
        cohort_id=cohort_id,
        cohort_ids=cohort_ids,
        allowed_student_ids=allowed_student_ids,
    )).scalars().unique())
    student_ids = [row.id for row in students]
    policy = active_readiness_policy(db, organization_id)
    snapshots = latest_readiness(db, organization_id, student_ids)
    if len(snapshots) < len(student_ids):
        recompute_readiness(db, organization_id, [student_id for student_id in student_ids if student_id not in snapshots])
        snapshots = latest_readiness(db, organization_id, student_ids)

    clients = {
        row.id: row for row in db.execute(
            select(Client).where(Client.organization_id == organization_id, Client.id.in_([student.client_id for student in students]))
        ).scalars()
    } if students else {}
    programs = {
        row.id: row for row in db.execute(select(CollegeProgram).where(CollegeProgram.organization_id == organization_id)).scalars()
    }
    cohort_rows = {
        row.id: row for row in db.execute(select(CollegeCohort).where(
            CollegeCohort.organization_id == organization_id,
            CollegeCohort.id.in_({student.cohort_id for student in students}) if students else CollegeCohort.id.is_(None),
        )).scalars()
    }
    departments = {
        row.id: row for row in db.execute(select(CollegeDepartment).where(CollegeDepartment.organization_id == organization_id)).scalars()
    }
    careers = {
        row.student_profile_id: row for row in db.execute(
            select(CollegeCareerProfile).where(
                CollegeCareerProfile.organization_id == organization_id,
                CollegeCareerProfile.student_profile_id.in_(student_ids) if student_ids else CollegeCareerProfile.id.is_(None),
            )
        ).scalars()
    }
    term_rows = list(db.execute(
        select(CollegeTermResult)
        .where(
            CollegeTermResult.organization_id == organization_id,
            CollegeTermResult.student_profile_id.in_(student_ids) if student_ids else CollegeTermResult.id.is_(None),
        )
        .order_by(CollegeTermResult.student_profile_id, CollegeTermResult.semester.desc())
    ).scalars())
    latest_terms = _first_by_student(term_rows)
    attendance_rows = list(db.execute(
        select(CollegeAttendanceSnapshot)
        .where(
            CollegeAttendanceSnapshot.organization_id == organization_id,
            CollegeAttendanceSnapshot.student_profile_id.in_(student_ids) if student_ids else CollegeAttendanceSnapshot.id.is_(None),
            CollegeAttendanceSnapshot.course_id.is_(None),
        )
        .order_by(CollegeAttendanceSnapshot.student_profile_id, CollegeAttendanceSnapshot.as_of.desc())
    ).scalars())
    latest_attendance = _first_by_student(attendance_rows)
    coding_rows = list(db.execute(
        select(CollegeCodingSnapshot)
        .where(
            CollegeCodingSnapshot.organization_id == organization_id,
            CollegeCodingSnapshot.student_profile_id.in_(student_ids) if student_ids else CollegeCodingSnapshot.id.is_(None),
        )
        .order_by(CollegeCodingSnapshot.student_profile_id, CollegeCodingSnapshot.captured_at.desc())
    ).scalars())
    latest_coding = _first_by_student(coding_rows)

    applications = list(db.execute(
        select(CollegePlacementApplication).where(
            CollegePlacementApplication.organization_id == organization_id,
            CollegePlacementApplication.student_profile_id.in_(student_ids) if student_ids else CollegePlacementApplication.id.is_(None),
        )
    ).scalars())
    application_ids = [row.id for row in applications]
    offers = list(db.execute(
        select(CollegePlacementOffer).where(
            CollegePlacementOffer.organization_id == organization_id,
            CollegePlacementOffer.application_id.in_(application_ids) if application_ids else CollegePlacementOffer.id.is_(None),
        )
    ).scalars())
    active_opportunities = list(db.execute(select(CollegePlacementOpportunity).where(
        CollegePlacementOpportunity.organization_id == organization_id,
        CollegePlacementOpportunity.status.in_(("published", "active")),
    )).scalars())
    active_drives = len(active_opportunities)

    minimum_coverage = float(policy.minimum_coverage_percent)
    readiness_ready_ids = {
        student_id for student_id, snapshot in snapshots.items()
        if snapshot.band == "ready" and float(snapshot.coverage_percent) >= minimum_coverage
    }
    placed_ids = {
        app.student_profile_id for app in applications
        if app.outcome in {"selected", "offered", "joined"}
    } | {
        careers_id for careers_id, career in careers.items()
        if career.placement_status in {"placed", "joined"}
    }
    ready_ids = readiness_ready_ids - placed_ids
    participating = {
        student_id for student_id in student_ids
        if careers.get(student_id) is None or careers[student_id].participation_status == "participating"
    }
    support_ids = {
        student_id for student_id in student_ids
        if student_id not in ready_ids and student_id not in placed_ids
    }

    readiness_distribution = Counter(
        snapshot.band if float(snapshot.coverage_percent) >= minimum_coverage else "insufficient_evidence"
        for snapshot in snapshots.values()
    )
    cgpa_buckets = Counter()
    for result in latest_terms.values():
        if result.cgpa is None:
            cgpa_buckets["No data"] += 1
        elif float(result.cgpa) >= 9:
            cgpa_buckets["9–10"] += 1
        elif float(result.cgpa) >= 8:
            cgpa_buckets["8–8.99"] += 1
        elif float(result.cgpa) >= 7:
            cgpa_buckets["7–7.99"] += 1
        else:
            cgpa_buckets["Below 7"] += 1
    coding_buckets = Counter()
    for student_id in student_ids:
        coding = latest_coding.get(student_id)
        total = coding.total_solved if coding and coding.total_solved is not None else None
        if total is None:
            coding_buckets["No profile"] += 1
        elif total >= 300:
            coding_buckets["300+"] += 1
        elif total >= 150:
            coding_buckets["150–299"] += 1
        elif total >= 50:
            coding_buckets["50–149"] += 1
        else:
            coding_buckets["Below 50"] += 1

    attendance_trend_values = defaultdict(list)
    for row in attendance_rows:
        if row.attendance_percent is not None:
            attendance_trend_values[row.as_of].append(float(row.attendance_percent))
    attendance_trend = [
        {
            "date": value_date.isoformat(),
            "label": value_date.strftime("%b %Y"),
            "attendance": round(sum(values) / len(values), 1),
        }
        for value_date, values in sorted(attendance_trend_values.items())
    ]
    coding_trend_values = defaultdict(list)
    for row in coding_rows:
        if row.total_solved is not None:
            coding_trend_values[row.captured_at.date()].append(row.total_solved)
    coding_trend = [
        {
            "date": value_date.isoformat(),
            "label": value_date.strftime("%b %Y"),
            "average_solved": round(sum(values) / len(values), 1),
        }
        for value_date, values in sorted(coding_trend_values.items())
    ]
    offer_outcomes = Counter(row.status for row in offers)

    stage_by_id = {row.id: row for row in ensure_default_pipeline(db, organization_id)}
    funnel = Counter(stage_by_id[app.current_stage_id].name if app.current_stage_id in stage_by_id else "Eligible" for app in applications)
    department_stats = defaultdict(lambda: {"students": 0, "ready": 0, "placed": 0, "attendance": []})
    for student in students:
        program = programs.get(student.program_id)
        if not program:
            continue
        bucket = department_stats[program.department_id]
        bucket["students"] += 1
        bucket["ready"] += int(student.id in ready_ids)
        bucket["placed"] += int(student.id in placed_ids)
        attendance = latest_attendance.get(student.id)
        if attendance and attendance.attendance_percent is not None:
            bucket["attendance"].append(float(attendance.attendance_percent))

    def student_card(student_id: str, reason: str, value=None):
        student = next((row for row in students if row.id == student_id), None)
        client = clients.get(student.client_id) if student else None
        return {
            "student_id": student_id,
            "client_id": student.client_id if student else None,
            "name": f"{client.first_name} {client.last_name}".strip() if client else "Student",
            "admission_number": student.admission_number if student else None,
            "reason": reason,
            "value": value,
        }

    attention = []
    for student_id in student_ids:
        attendance = latest_attendance.get(student_id)
        term = latest_terms.get(student_id)
        coding = latest_coding.get(student_id)
        career = careers.get(student_id)
        if attendance and attendance.attendance_percent is not None and float(attendance.attendance_percent) < 75:
            attention.append(student_card(student_id, "Low attendance", round(float(attendance.attendance_percent), 1)))
        if term and (term.active_backlogs or 0) > 0:
            attention.append(student_card(student_id, "Active backlogs", term.active_backlogs))
        if coding and coding.captured_at < datetime.now(timezone.utc) - timedelta(days=14):
            attention.append(student_card(student_id, "Coding profile is stale", coding.captured_at.isoformat()))
        if not career or career.resume_status in {"missing", "draft"}:
            attention.append(student_card(student_id, "Resume incomplete", career.resume_status if career else "missing"))
        snapshot = snapshots.get(student_id)
        if snapshot and float(snapshot.coverage_percent) < minimum_coverage:
            attention.append(student_card(student_id, "Readiness evidence needs review", float(snapshot.coverage_percent)))
    stalled_cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    for application in applications:
        effective_eligibility = application.eligibility_override_status or application.eligibility_status
        if effective_eligibility == "needs_review":
            item = student_card(application.student_profile_id, "Eligibility needs review")
            item.update({"application_id": application.id, "opportunity_id": application.opportunity_id})
            attention.append(item)
        stage = stage_by_id.get(application.current_stage_id)
        updated_at = application.updated_at
        if stage and stage.stage_type == "active" and updated_at and updated_at < stalled_cutoff:
            item = student_card(application.student_profile_id, "Placement application is stalled", updated_at.isoformat())
            item.update({"application_id": application.id, "opportunity_id": application.opportunity_id})
            attention.append(item)

    scoped_program_ids = None
    scoped_cohort_ids = None
    scoped_department_ids = None
    if allowed_student_ids is not None:
        scoped_pairs = db.execute(select(
            CollegeStudentProfile.program_id,
            CollegeStudentProfile.cohort_id,
        ).where(
            CollegeStudentProfile.organization_id == organization_id,
            CollegeStudentProfile.id.in_(allowed_student_ids),
        )).all()
        scoped_program_ids = {row.program_id for row in scoped_pairs}
        scoped_cohort_ids = {row.cohort_id for row in scoped_pairs}
        scoped_department_ids = {
            programs[program_id_value].department_id
            for program_id_value in scoped_program_ids
            if program_id_value in programs
        }
        active_opportunities = [
            row for row in active_opportunities
            if opportunity_rules_match_scope(
                row.eligibility_rules,
                department_ids=scoped_department_ids,
                program_ids=scoped_program_ids,
                cohort_ids=scoped_cohort_ids,
            )
        ]
        active_drives = len(active_opportunities)

    company_ids = {row.company_id for row in active_opportunities}
    companies = {
        row.id: row for row in db.execute(
            select(CollegePlacementCompany).where(
                CollegePlacementCompany.organization_id == organization_id,
                CollegePlacementCompany.id.in_(company_ids) if company_ids else CollegePlacementCompany.id.is_(None),
            )
        ).scalars()
    }
    application_counts = Counter(row.opportunity_id for row in applications)
    now = datetime.now(timezone.utc)
    active_drive_deadlines = []
    for opportunity in sorted(
        active_opportunities,
        key=lambda row: row.deadline_at or row.drive_at or datetime.max.replace(tzinfo=timezone.utc),
    ):
        milestone = opportunity.deadline_at or opportunity.drive_at
        if milestone and milestone < now - timedelta(days=1):
            continue
        company = companies.get(opportunity.company_id)
        active_drive_deadlines.append({
            "id": opportunity.id,
            "title": opportunity.title,
            "company": company.name if company else "Recruiting company",
            "deadline_at": opportunity.deadline_at.isoformat() if opportunity.deadline_at else None,
            "drive_at": opportunity.drive_at.isoformat() if opportunity.drive_at else None,
            "application_count": application_counts.get(opportunity.id, 0),
            "action_url": f"/app/college?section=drives&opportunity={opportunity.id}",
        })
        if len(active_drive_deadlines) == 5:
            break

    brief = []
    insufficient_evidence = sum(
        1 for row in snapshots.values()
        if float(row.coverage_percent) < minimum_coverage
    )
    stalled_applications = sum(
        1 for row in attention if row["reason"] == "Placement application is stalled"
    )
    upcoming_deadlines = sum(
        1 for row in active_opportunities
        if row.deadline_at and now <= row.deadline_at <= now + timedelta(days=7)
    )
    if support_ids:
        brief.append({
            "key": "support",
            "title": f"{len(support_ids)} students need readiness support",
            "detail": "Prioritize missing evidence, low attendance, backlogs, and incomplete profiles.",
            "evidence_count": len(support_ids),
            "action_label": "Review support queue",
            "action_url": "/app/college?section=readiness",
            "tone": "warning",
        })
    if upcoming_deadlines:
        brief.append({
            "key": "deadlines",
            "title": f"{upcoming_deadlines} drive deadlines fall within seven days",
            "detail": "Review eligible candidates and unresolved applications before submissions close.",
            "evidence_count": upcoming_deadlines,
            "action_label": "Open active drives",
            "action_url": "/app/college?section=drives",
            "tone": "accent",
        })
    if stalled_applications:
        brief.append({
            "key": "stalled",
            "title": f"{stalled_applications} applications have not moved for 14 days",
            "detail": "Confirm the next stage, record an outcome, or assign a follow-up.",
            "evidence_count": stalled_applications,
            "action_label": "Review pipeline",
            "action_url": "/app/college",
            "tone": "warning",
        })
    if insufficient_evidence and len(brief) < 3:
        brief.append({
            "key": "coverage",
            "title": f"{insufficient_evidence} students have insufficient readiness evidence",
            "detail": f"They remain visible but are excluded from ranking below {minimum_coverage:g}% coverage.",
            "evidence_count": insufficient_evidence,
            "action_label": "Review evidence",
            "action_url": "/app/college?section=evidence",
            "tone": "neutral",
        })
    filters = {
        "academic_years": list(db.execute(select(CollegeTerm.academic_year).where(CollegeTerm.organization_id == organization_id).distinct().order_by(CollegeTerm.academic_year.desc())).scalars()),
        "graduation_years": sorted({cohort.graduation_year for cohort in cohort_rows.values()}, reverse=True),
        "departments": [{"id": row.id, "name": row.name, "code": row.code} for row in departments.values() if row.is_active and (scoped_department_ids is None or row.id in scoped_department_ids)],
        "programs": [{"id": row.id, "department_id": row.department_id, "name": row.name, "code": row.code} for row in programs.values() if row.is_active and (scoped_program_ids is None or row.id in scoped_program_ids)],
        "cohorts": [{"id": row.id, "program_id": row.program_id, "name": row.name, "code": row.code, "section": row.section or "General", "graduation_year": row.graduation_year} for row in db.execute(select(CollegeCohort).where(CollegeCohort.organization_id == organization_id, CollegeCohort.is_active.is_(True))).scalars() if scoped_cohort_ids is None or row.id in scoped_cohort_ids],
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": filters,
        "metrics": {
            "participating_students": len(participating),
            "placement_ready": len(ready_ids),
            "needs_support": len(support_ids),
            "placed_students": len(placed_ids),
            "active_drives": active_drives,
            "offers": len(offers),
        },
        "readiness_distribution": [{"label": key.replace("_", " ").title(), "key": key, "value": value} for key, value in readiness_distribution.items()],
        "cgpa_distribution": [{"label": key, "value": value} for key, value in cgpa_buckets.items()],
        "coding_progress": [{"label": key, "value": value} for key, value in coding_buckets.items()],
        "attendance_trend": attendance_trend,
        "coding_trend": coding_trend,
        "placement_funnel": [{"stage_id": stage.id, "label": stage.name, "value": funnel.get(stage.name, 0)} for stage in stage_by_id.values() if stage.is_enabled],
        "offer_outcomes": [{"key": key, "label": key.replace("_", " ").title(), "value": value} for key, value in offer_outcomes.items()],
        "department_comparison": [
            {
                "department_id": department_id_value,
                "department": departments[department_id_value].name if department_id_value in departments else "Department",
                "students": values["students"],
                "ready": values["ready"],
                "placed": values["placed"],
                "attendance": round(sum(values["attendance"]) / len(values["attendance"]), 1) if values["attendance"] else None,
            }
            for department_id_value, values in department_stats.items()
        ],
        "active_drive_deadlines": active_drive_deadlines,
        "brief": brief[:3],
        "attention": attention[:30],
        "coverage": {
            "rankable": sum(1 for row in snapshots.values() if float(row.coverage_percent) >= minimum_coverage),
            "total": len(student_ids),
            "minimum_percent": minimum_coverage,
        },
    }


def serialize_snapshot(row: CollegeReadinessSnapshot | None, policy: CollegeReadinessPolicy | None = None) -> dict | None:
    if not row:
        return None
    minimum = float(policy.minimum_coverage_percent) if policy else 60
    return {
        "id": row.id,
        "score": _float(row.score),
        "coverage_percent": _float(row.coverage_percent),
        "band": row.band,
        "rankable": row.score is not None and float(row.coverage_percent) >= minimum,
        "factors": row.factors,
        "missing_evidence": row.missing_evidence,
        "source_records": row.source_records,
        "policy_version": row.policy_version,
        "calculated_at": row.calculated_at.isoformat(),
    }


def placement_leaderboards(
    db: Session,
    organization_id: str,
    *,
    department_id: str | None = None,
    program_id: str | None = None,
    cohort_id: str | None = None,
    window_days: int = 30,
    limit: int = 25,
    allowed_student_ids: set[str] | None = None,
) -> dict:
    students = list(db.execute(student_query(
        organization_id,
        department_id=department_id,
        program_id=program_id,
        cohort_id=cohort_id,
        allowed_student_ids=allowed_student_ids,
    )).scalars().unique())
    ids = [row.id for row in students]
    client_ids = [row.client_id for row in students]
    clients = {row.id: row for row in db.execute(select(Client).where(Client.id.in_(client_ids))).scalars()} if client_ids else {}
    programs = {row.id: row for row in db.execute(select(CollegeProgram).where(CollegeProgram.organization_id == organization_id)).scalars()}
    departments = {row.id: row for row in db.execute(select(CollegeDepartment).where(CollegeDepartment.organization_id == organization_id)).scalars()}
    policy = active_readiness_policy(db, organization_id)
    latest_scores = latest_readiness(db, organization_id, ids)
    if len(latest_scores) < len(ids):
        recompute_readiness(db, organization_id, [student_id for student_id in ids if student_id not in latest_scores])
        latest_scores = latest_readiness(db, organization_id, ids)

    term_rows = list(db.execute(
        select(CollegeTermResult)
        .where(CollegeTermResult.organization_id == organization_id, CollegeTermResult.student_profile_id.in_(ids) if ids else CollegeTermResult.id.is_(None))
        .order_by(
            CollegeTermResult.student_profile_id,
            CollegeTermResult.semester.desc(),
            CollegeTermResult.published_on.desc().nullslast(),
            CollegeTermResult.created_at.desc(),
        )
    ).scalars())
    latest_terms = _first_by_student(term_rows)
    coding_rows = list(db.execute(
        select(CollegeCodingSnapshot)
        .where(CollegeCodingSnapshot.organization_id == organization_id, CollegeCodingSnapshot.student_profile_id.in_(ids) if ids else CollegeCodingSnapshot.id.is_(None))
        .order_by(CollegeCodingSnapshot.student_profile_id, CollegeCodingSnapshot.captured_at.desc())
    ).scalars())
    coding_groups = defaultdict(list)
    for row in coding_rows:
        coding_groups[row.student_profile_id].append(row)
    readiness_rows = list(db.execute(
        select(CollegeReadinessSnapshot)
        .where(CollegeReadinessSnapshot.organization_id == organization_id, CollegeReadinessSnapshot.student_profile_id.in_(ids) if ids else CollegeReadinessSnapshot.id.is_(None))
        .order_by(CollegeReadinessSnapshot.student_profile_id, CollegeReadinessSnapshot.calculated_at.desc())
    ).scalars())
    readiness_groups = defaultdict(list)
    for row in readiness_rows:
        readiness_groups[row.student_profile_id].append(row)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, min(window_days, 365)))

    def identity(student: CollegeStudentProfile) -> dict:
        client = clients.get(student.client_id)
        program = programs.get(student.program_id)
        department = departments.get(program.department_id) if program else None
        return {
            "student_id": student.id,
            "client_id": student.client_id,
            "name": f"{client.first_name} {client.last_name}".strip() if client else "Student",
            "admission_number": student.admission_number,
            "program": program.name if program else None,
            "department": department.name if department else None,
        }

    coding_board = []
    academic_board = []
    readiness_board = []
    improvement_board = []
    for student in students:
        base = identity(student)
        coding = coding_groups[student.id][0] if coding_groups[student.id] else None
        if coding:
            difficulty_points = (coding.easy_solved or 0) + 2 * (coding.medium_solved or 0) + 3 * (coding.hard_solved or 0)
            coding_board.append({
                **base,
                "score": round(difficulty_points + max(0, float(coding.contest_rating or 0) - 1200) / 10, 2),
                "total_solved": coding.total_solved,
                "easy": coding.easy_solved,
                "medium": coding.medium_solved,
                "hard": coding.hard_solved,
                "contest_rating": _float(coding.contest_rating),
                "captured_at": coding.captured_at.isoformat(),
            })
        term = latest_terms.get(student.id)
        if term and term.cgpa is not None:
            academic_board.append({
                **base,
                "score": round(float(term.cgpa) * 10 - min(25, (term.active_backlogs or 0) * 5), 2),
                "cgpa": _float(term.cgpa),
                "sgpa": _float(term.sgpa),
                "active_backlogs": term.active_backlogs,
                "semester": term.semester,
            })
        readiness = latest_scores.get(student.id)
        if readiness:
            readiness_board.append({
                **base,
                "score": _float(readiness.score),
                "coverage_percent": _float(readiness.coverage_percent),
                "band": readiness.band,
                "rankable": readiness.score is not None and float(readiness.coverage_percent) >= float(policy.minimum_coverage_percent),
            })
        coding_history = coding_groups[student.id]
        current_coding = coding_history[0] if coding_history else None
        previous_coding = next((row for row in coding_history if row.captured_at <= cutoff), None)
        readiness_history = readiness_groups[student.id]
        current_readiness = readiness_history[0] if readiness_history else None
        previous_readiness = next((row for row in readiness_history if row.calculated_at <= cutoff), None)
        solved_change = None
        readiness_change = None
        if current_coding and previous_coding and current_coding.total_solved is not None and previous_coding.total_solved is not None:
            solved_change = current_coding.total_solved - previous_coding.total_solved
        if current_readiness and previous_readiness and current_readiness.score is not None and previous_readiness.score is not None:
            readiness_change = float(current_readiness.score) - float(previous_readiness.score)
        if solved_change is not None or readiness_change is not None:
            improvement_board.append({
                **base,
                "score": round((solved_change or 0) + (readiness_change or 0) * 2, 2),
                "solved_change": solved_change,
                "readiness_change": round(readiness_change, 2) if readiness_change is not None else None,
                "window_days": window_days,
            })

    coding_board.sort(key=lambda row: (row["score"], row["total_solved"] or 0), reverse=True)
    academic_board.sort(key=lambda row: (row["score"], row["cgpa"] or 0), reverse=True)
    readiness_board.sort(key=lambda row: (row["rankable"], row["score"] or -1, row["coverage_percent"]), reverse=True)
    improvement_board.sort(key=lambda row: row["score"], reverse=True)
    for board in (coding_board, academic_board, readiness_board, improvement_board):
        for rank, row in enumerate(board[:limit], start=1):
            row["rank"] = rank
    return {
        "coding": coding_board[:limit],
        "academics": academic_board[:limit],
        "readiness": readiness_board[:limit],
        "improvement": improvement_board[:limit],
        "policy": {
            "version": policy.version,
            "minimum_coverage_percent": _float(policy.minimum_coverage_percent),
        },
    }


def student_intelligence(db: Session, organization_id: str, student_id: str) -> dict | None:
    pair = db.execute(
        select(CollegeStudentProfile, Client, CollegeProgram, CollegeDepartment, CollegeCohort)
        .join(Client, Client.id == CollegeStudentProfile.client_id)
        .join(CollegeProgram, CollegeProgram.id == CollegeStudentProfile.program_id)
        .join(CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id)
        .join(CollegeCohort, CollegeCohort.id == CollegeStudentProfile.cohort_id)
        .where(
            CollegeStudentProfile.id == student_id,
            CollegeStudentProfile.organization_id == organization_id,
        )
    ).first()
    if not pair:
        return None
    student, client, program, department, cohort = pair
    career = db.execute(select(CollegeCareerProfile).where(
        CollegeCareerProfile.organization_id == organization_id,
        CollegeCareerProfile.student_profile_id == student_id,
    )).scalar_one_or_none()
    terms = list(db.execute(
        select(CollegeTermResult)
        .where(CollegeTermResult.organization_id == organization_id, CollegeTermResult.student_profile_id == student_id)
        .order_by(CollegeTermResult.semester.desc())
    ).scalars())
    attendance = list(db.execute(
        select(CollegeAttendanceSnapshot)
        .where(CollegeAttendanceSnapshot.organization_id == organization_id, CollegeAttendanceSnapshot.student_profile_id == student_id)
        .order_by(CollegeAttendanceSnapshot.as_of.desc())
    ).scalars())
    coding_account = db.execute(select(CollegeCodingAccount).where(
        CollegeCodingAccount.organization_id == organization_id,
        CollegeCodingAccount.student_profile_id == student_id,
        CollegeCodingAccount.is_active.is_(True),
    )).scalars().first()
    coding = list(db.execute(
        select(CollegeCodingSnapshot)
        .where(CollegeCodingSnapshot.organization_id == organization_id, CollegeCodingSnapshot.student_profile_id == student_id)
        .order_by(CollegeCodingSnapshot.captured_at.desc())
        .limit(90)
    ).scalars())
    evidence = list(db.execute(
        select(CollegeCareerEvidence)
        .where(CollegeCareerEvidence.organization_id == organization_id, CollegeCareerEvidence.student_profile_id == student_id)
        .order_by(CollegeCareerEvidence.evidence_type, CollegeCareerEvidence.created_at.desc())
    ).scalars())
    assessments = list(db.execute(
        select(CollegePlacementAssessment)
        .where(CollegePlacementAssessment.organization_id == organization_id, CollegePlacementAssessment.student_profile_id == student_id)
        .order_by(CollegePlacementAssessment.assessed_on.desc().nullslast())
    ).scalars())
    preparation = list(db.execute(
        select(CollegePreparationActivity)
        .where(CollegePreparationActivity.organization_id == organization_id, CollegePreparationActivity.student_profile_id == student_id)
        .order_by(CollegePreparationActivity.occurred_on.desc().nullslast())
    ).scalars())
    interventions = list(db.execute(
        select(CollegeStudentIntervention)
        .where(
            CollegeStudentIntervention.organization_id == organization_id,
            CollegeStudentIntervention.student_profile_id == student_id,
        )
        .order_by(CollegeStudentIntervention.created_at.desc())
    ).scalars())
    policy = active_readiness_policy(db, organization_id)
    readiness = latest_readiness(db, organization_id, [student_id]).get(student_id)
    if not readiness:
        readiness = recompute_readiness(db, organization_id, [student_id])[0]
    fee_clearance = fee_clearance_by_student(db, organization_id, [student_id])[student_id]

    application_rows = db.execute(
        select(
            CollegePlacementApplication,
            CollegePlacementOpportunity,
            CollegePlacementCompany,
            CollegePipelineStage,
        )
        .join(CollegePlacementOpportunity, CollegePlacementOpportunity.id == CollegePlacementApplication.opportunity_id)
        .join(CollegePlacementCompany, CollegePlacementCompany.id == CollegePlacementOpportunity.company_id)
        .outerjoin(CollegePipelineStage, CollegePipelineStage.id == CollegePlacementApplication.current_stage_id)
        .where(
            CollegePlacementApplication.organization_id == organization_id,
            CollegePlacementApplication.student_profile_id == student_id,
        )
        .order_by(CollegePlacementApplication.updated_at.desc())
    ).all()
    application_ids = [row[0].id for row in application_rows]
    interviews = defaultdict(list)
    offers = defaultdict(list)
    if application_ids:
        for row in db.execute(select(CollegePlacementInterview).where(CollegePlacementInterview.application_id.in_(application_ids))).scalars():
            interviews[row.application_id].append(row)
        for row in db.execute(select(CollegePlacementOffer).where(CollegePlacementOffer.application_id.in_(application_ids))).scalars():
            offers[row.application_id].append(row)

    activities = []
    for row in terms:
        activities.append({"type": "term_result", "title": f"Semester {row.semester} result", "detail": f"CGPA {row.cgpa}" if row.cgpa is not None else "Result imported", "at": (row.published_on or row.created_at.date()).isoformat(), "source_id": row.id})
    for row in coding[:10]:
        activities.append({"type": "coding_snapshot", "title": "Coding profile synchronized", "detail": f"{row.total_solved or 0} problems solved", "at": row.captured_at.isoformat(), "source_id": row.id})
    for row in interventions:
        activities.append({"type": "intervention", "title": row.title, "detail": f"{row.priority.title()} priority / {row.status.replace('_', ' ').title()}", "at": (row.resolved_at or row.updated_at or row.created_at).isoformat(), "source_id": row.id})
    if application_ids:
        events = db.execute(
            select(CollegeApplicationStageEvent, CollegePipelineStage)
            .join(CollegePipelineStage, CollegePipelineStage.id == CollegeApplicationStageEvent.to_stage_id)
            .where(CollegeApplicationStageEvent.application_id.in_(application_ids))
            .order_by(CollegeApplicationStageEvent.occurred_at.desc())
        ).all()
        for event, stage in events:
            activities.append({"type": "application_stage", "title": f"Moved to {stage.name}", "detail": event.reason, "at": event.occurred_at.isoformat(), "source_id": event.id})
    activities.sort(key=lambda item: item["at"], reverse=True)

    return {
        "student": {
            "id": student.id,
            "client_id": student.client_id,
            "name": f"{client.first_name} {client.last_name}".strip(),
            "email": client.email,
            "phone": client.phone,
            "admission_number": student.admission_number,
            "roll_number": student.roll_number,
            "semester": student.current_semester,
            "status": student.status,
            "program": {"id": program.id, "name": program.name, "code": program.code},
            "department": {"id": department.id, "name": department.name, "code": department.code},
            "cohort": {"id": cohort.id, "name": cohort.name, "code": cohort.code, "admission_year": cohort.admission_year, "graduation_year": cohort.graduation_year, "section": cohort.section or "General"},
        },
        "career": {
            "participation_status": career.participation_status,
            "graduation_year": cohort.graduation_year,
            "preferred_roles": career.preferred_roles,
            "preferred_locations": career.preferred_locations,
            "linkedin_url": career.linkedin_url,
            "github_url": career.github_url,
            "portfolio_url": career.portfolio_url,
            "resume_status": career.resume_status,
            "placement_status": career.placement_status,
        } if career else None,
        "readiness": serialize_snapshot(readiness, policy),
        "fee_clearance": {
            "status": fee_clearance["status"],
            "assigned_count": fee_clearance["assigned_count"],
            "cleared_count": fee_clearance["cleared_count"],
            "open_invoice_count": fee_clearance["open_invoice_count"],
        },
        "academics": [
            {
                "id": row.id, "semester": row.semester, "sgpa": _float(row.sgpa),
                "cgpa": _float(row.cgpa), "active_backlogs": row.active_backlogs,
                "total_backlogs": row.total_backlogs, "credits_earned": row.credits_earned,
                "published_on": row.published_on.isoformat() if row.published_on else None,
            }
            for row in terms
        ],
        "attendance": [
            {
                "id": row.id, "term_id": row.term_id, "course_id": row.course_id,
                "scope": row.scope_key, "classes_held": row.classes_held,
                "classes_attended": row.classes_attended,
                "attendance_percent": _float(row.attendance_percent), "as_of": row.as_of.isoformat(),
            }
            for row in attendance
        ],
        "coding": {
            "account": {
                "id": coding_account.id, "platform": coding_account.platform,
                "username": coding_account.username, "verification_status": coding_account.verification_status,
                "consent_status": coding_account.consent_status, "sync_status": coding_account.sync_status,
                "last_success_at": coding_account.last_success_at.isoformat() if coding_account.last_success_at else None,
            } if coding_account else None,
            "snapshots": [
                {
                    "id": row.id, "captured_at": row.captured_at.isoformat(),
                    "easy": row.easy_solved, "medium": row.medium_solved, "hard": row.hard_solved,
                    "total": row.total_solved, "contest_rating": _float(row.contest_rating),
                    "contest_rank": row.contest_rank, "global_rank": row.global_rank,
                    "languages": row.languages,
                }
                for row in coding
            ],
        },
        "evidence": {
            kind: [
                {
                    "id": row.id, "title": row.title, "issuer": row.issuer,
                    "description": row.description, "url": row.evidence_url,
                    "proficiency": row.proficiency, "verified": row.is_verified,
                    "completed_on": row.completed_on.isoformat() if row.completed_on else None,
                    "details": row.details,
                }
                for row in evidence if row.evidence_type == kind
            ]
            for kind in ("skill", "project", "certification")
        },
        "assessments": [
            {"id": row.id, "type": row.assessment_type, "title": row.title, "score_percent": _float(row.score_percent), "assessed_on": row.assessed_on.isoformat() if row.assessed_on else None, "provider": row.provider}
            for row in assessments
        ],
        "preparation": [
            {"id": row.id, "type": row.activity_type, "title": row.title, "status": row.status, "occurred_on": row.occurred_on.isoformat() if row.occurred_on else None, "outcome_score": _float(row.outcome_score)}
            for row in preparation
        ],
        "interventions": [
            {
                "id": row.id, "reason_code": row.reason_code, "title": row.title,
                "note": row.note, "status": row.status, "priority": row.priority,
                "assigned_to_user_id": row.assigned_to_user_id,
                "due_on": row.due_on.isoformat() if row.due_on else None,
                "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
                "resolution_note": row.resolution_note,
            }
            for row in interventions
        ],
        "applications": [
            {
                "id": application.id,
                "opportunity": {"id": opportunity.id, "title": opportunity.title, "status": opportunity.status},
                "company": {"id": company.id, "name": company.name},
                "stage": {"id": stage.id, "name": stage.name, "slug": stage.slug} if stage else None,
                "eligibility_status": application.eligibility_override_status or application.eligibility_status,
                "eligibility_evidence": application.eligibility_evidence,
                "applied_at": application.applied_at.isoformat() if application.applied_at else None,
                "outcome": application.outcome,
                "interviews": [
                    {"id": row.id, "type": row.interview_type, "scheduled_at": row.scheduled_at.isoformat() if row.scheduled_at else None, "status": row.status, "score_percent": _float(row.score_percent)}
                    for row in interviews[application.id]
                ],
                "offers": [
                    {"id": row.id, "role": row.offered_role, "package_paise": row.package_paise, "offered_on": row.offered_on.isoformat() if row.offered_on else None, "joining_on": row.joining_on.isoformat() if row.joining_on else None, "status": row.status}
                    for row in offers[application.id]
                ],
            }
            for application, opportunity, company, stage in application_rows
        ],
        "activity": activities[:100],
    }


def student_directory_summary(
    db: Session,
    organization_id: str,
    *,
    graduation_year: int | None = None,
    department_id: str | None = None,
    program_id: str | None = None,
    cohort_id: str | None = None,
    cohort_ids: set[str] | list[str] | tuple[str, ...] | None = None,
    allowed_student_ids: set[str] | None = None,
    include_readiness: bool = False,
    readiness_allowed_student_ids: set[str] | None = None,
    include_placements: bool = False,
    placement_allowed_student_ids: set[str] | None = None,
) -> dict:
    """Return directory metrics without widening any optional evidence domain."""
    student_ids = set(db.execute(
        student_query(
            organization_id,
            graduation_year=graduation_year,
            department_id=department_id,
            program_id=program_id,
            cohort_id=cohort_id,
            cohort_ids=cohort_ids,
            allowed_student_ids=allowed_student_ids,
        )
        .with_only_columns(CollegeStudentProfile.id)
        .order_by(None)
    ).scalars())

    def narrowed(allowed_ids: set[str] | None) -> set[str]:
        return set(student_ids) if allowed_ids is None else student_ids & set(allowed_ids)

    placement_scope_ids = narrowed(placement_allowed_student_ids) if include_placements else set()
    placed_ids: set[str] = set()
    if placement_scope_ids:
        careers = list(db.execute(select(CollegeCareerProfile).where(
            CollegeCareerProfile.organization_id == organization_id,
            CollegeCareerProfile.student_profile_id.in_(placement_scope_ids),
        )).scalars())
        applications = list(db.execute(select(CollegePlacementApplication).where(
            CollegePlacementApplication.organization_id == organization_id,
            CollegePlacementApplication.student_profile_id.in_(placement_scope_ids),
        )).scalars())
        placed_ids = {
            row.student_profile_id for row in applications
            if row.outcome in {"selected", "offered", "joined"}
        } | {
            row.student_profile_id for row in careers
            if row.placement_status in {"placed", "joined"}
        }

    readiness_metrics_available = include_readiness and include_placements
    placement_ready = None
    needs_support = None
    if readiness_metrics_available:
        readiness_scope_ids = narrowed(readiness_allowed_student_ids)
        metric_scope_ids = readiness_scope_ids & placement_scope_ids
        policy = active_readiness_policy(db, organization_id)
        snapshots = latest_readiness(db, organization_id, list(metric_scope_ids))
        minimum_coverage = float(policy.minimum_coverage_percent)
        ready_ids = {
            student_id for student_id, snapshot in snapshots.items()
            if snapshot.band == "ready" and float(snapshot.coverage_percent) >= minimum_coverage
        } - placed_ids
        support_ids = {
            student_id for student_id, snapshot in snapshots.items()
            if snapshot.band == "needs_support" and float(snapshot.coverage_percent) >= minimum_coverage
        } - placed_ids
        placement_ready = len(ready_ids)
        needs_support = len(support_ids)

    return {
        "total_students": len(student_ids),
        "placement_ready": placement_ready,
        "needs_support": needs_support,
        "placed_students": len(placed_ids) if include_placements else None,
        "scope": {
            "readiness_students": len(
                narrowed(readiness_allowed_student_ids)
            ) if include_readiness else None,
            "placement_students": len(placement_scope_ids) if include_placements else None,
        },
    }


def student_roster(
    db: Session,
    organization_id: str,
    *,
    q: str | None = None,
    department_id: str | None = None,
    program_id: str | None = None,
    cohort_id: str | None = None,
    cohort_ids: set[str] | list[str] | tuple[str, ...] | None = None,
    graduation_years: list[int] | tuple[int, ...] | set[int] | None = None,
    section: str | None = None,
    readiness_band: str | None = None,
    placement_status: str | None = None,
    sort: str = "name",
    limit: int = 50,
    offset: int = 0,
    cursor_values: dict | None = None,
    allowed_student_ids: set[str] | None = None,
) -> dict:
    policy = active_readiness_policy(db, organization_id)
    latest_readiness_rows = select(
        CollegeReadinessSnapshot.student_profile_id.label("student_profile_id"),
        CollegeReadinessSnapshot.score.label("score"),
        CollegeReadinessSnapshot.coverage_percent.label("coverage_percent"),
        CollegeReadinessSnapshot.band.label("band"),
        func.row_number().over(
            partition_by=CollegeReadinessSnapshot.student_profile_id,
            order_by=CollegeReadinessSnapshot.calculated_at.desc(),
        ).label("position"),
    ).where(CollegeReadinessSnapshot.organization_id == organization_id).subquery()
    effective_band = case(
        (
            and_(
                latest_readiness_rows.c.score.is_not(None),
                latest_readiness_rows.c.coverage_percent >= policy.minimum_coverage_percent,
            ),
            latest_readiness_rows.c.band,
        ),
        else_="insufficient_evidence",
    )
    latest_term_rows = select(
        CollegeTermResult.student_profile_id.label("student_profile_id"),
        CollegeTermResult.cgpa.label("cgpa"),
        func.row_number().over(
            partition_by=CollegeTermResult.student_profile_id,
            order_by=(
                CollegeTermResult.semester.desc(),
                CollegeTermResult.published_on.desc().nullslast(),
                CollegeTermResult.created_at.desc(),
            ),
        ).label("position"),
    ).where(CollegeTermResult.organization_id == organization_id).subquery()
    academic_value = func.coalesce(latest_term_rows.c.cgpa, Decimal("-1"))
    placed_application_students = select(
        CollegePlacementApplication.student_profile_id.label("student_profile_id"),
    ).where(
        CollegePlacementApplication.organization_id == organization_id,
        CollegePlacementApplication.outcome.in_(("selected", "offered", "joined")),
    ).distinct().subquery()
    query = (
        select(CollegeStudentProfile, Client, CollegeProgram, CollegeDepartment, CollegeCohort)
        .join(Client, Client.id == CollegeStudentProfile.client_id)
        .join(CollegeProgram, CollegeProgram.id == CollegeStudentProfile.program_id)
        .join(CollegeDepartment, CollegeDepartment.id == CollegeProgram.department_id)
        .join(CollegeCohort, CollegeCohort.id == CollegeStudentProfile.cohort_id)
        .outerjoin(latest_readiness_rows, and_(
            latest_readiness_rows.c.student_profile_id == CollegeStudentProfile.id,
            latest_readiness_rows.c.position == 1,
        ))
        .outerjoin(latest_term_rows, and_(
            latest_term_rows.c.student_profile_id == CollegeStudentProfile.id,
            latest_term_rows.c.position == 1,
        ))
        .outerjoin(
            CollegeCareerProfile,
            CollegeCareerProfile.student_profile_id == CollegeStudentProfile.id,
        )
        .outerjoin(
            placed_application_students,
            placed_application_students.c.student_profile_id == CollegeStudentProfile.id,
        )
        .where(
            CollegeStudentProfile.organization_id == organization_id,
            CollegeStudentProfile.status == "active",
        )
    )
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            Client.first_name.ilike(like)
            | Client.last_name.ilike(like)
            | CollegeStudentProfile.admission_number.ilike(like)
            | CollegeStudentProfile.roll_number.ilike(like)
        )
    if department_id:
        query = query.where(CollegeDepartment.id == department_id)
    if program_id:
        query = query.where(CollegeProgram.id == program_id)
    if cohort_id:
        query = query.where(CollegeCohort.id == cohort_id)
    if cohort_ids:
        query = query.where(CollegeCohort.id.in_(set(cohort_ids)))
    if graduation_years:
        query = query.where(CollegeCohort.graduation_year.in_({int(year) for year in graduation_years}))
    if section:
        query = query.where(func.lower(func.trim(CollegeCohort.section)) == section.strip().casefold())
    if allowed_student_ids is not None:
        query = query.where(CollegeStudentProfile.id.in_(allowed_student_ids))
    if readiness_band:
        query = query.where(effective_band == readiness_band)
    if placement_status == "placed":
        query = query.where(or_(
            CollegeCareerProfile.placement_status.in_(("placed", "joined")),
            placed_application_students.c.student_profile_id.is_not(None),
        ))
    elif placement_status == "unplaced":
        query = query.where(and_(
            or_(
                CollegeCareerProfile.id.is_(None),
                CollegeCareerProfile.placement_status.notin_(("placed", "joined")),
            ),
            placed_application_students.c.student_profile_id.is_(None),
        ))
    elif placement_status == "not_participating":
        query = query.where(CollegeCareerProfile.participation_status == "not_participating")
    elif placement_status == "seeking":
        query = query.where(
            CollegeCareerProfile.placement_status == "seeking",
            placed_application_students.c.student_profile_id.is_(None),
        )
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    if cursor_values:
        first = str(cursor_values.get("first") or "")
        last = str(cursor_values.get("last") or "")
        student_id = str(cursor_values.get("id") or "")
        name_after = or_(
            func.lower(Client.first_name) > first,
            and_(func.lower(Client.first_name) == first, func.lower(Client.last_name) > last),
            and_(func.lower(Client.first_name) == first, func.lower(Client.last_name) == last, CollegeStudentProfile.id > student_id),
        )
        if sort == "academics_desc":
            metric = Decimal(str(cursor_values.get("metric", "-1")))
            query = query.where(or_(academic_value < metric, and_(academic_value == metric, name_after)))
        else:
            query = query.where(name_after)
    page_size = min(max(int(limit), 1), 100)
    order_by = (
        (academic_value.desc(), func.lower(Client.first_name), func.lower(Client.last_name), CollegeStudentProfile.id)
        if sort == "academics_desc"
        else (func.lower(Client.first_name), func.lower(Client.last_name), CollegeStudentProfile.id)
    )
    pairs = db.execute(
        query.order_by(*order_by)
        .offset(offset if not cursor_values else 0)
        .limit(page_size + 1)
    ).all()
    has_more = len(pairs) > page_size
    pairs = pairs[:page_size]
    ids = [student.id for student, *_ in pairs]
    readiness = latest_readiness(db, organization_id, ids)
    term_rows = list(db.execute(
        select(CollegeTermResult)
        .where(CollegeTermResult.organization_id == organization_id, CollegeTermResult.student_profile_id.in_(ids) if ids else CollegeTermResult.id.is_(None))
        .order_by(
            CollegeTermResult.student_profile_id,
            CollegeTermResult.semester.desc(),
            CollegeTermResult.published_on.desc().nullslast(),
            CollegeTermResult.created_at.desc(),
        )
    ).scalars())
    terms = _first_by_student(term_rows)
    attendance_rows = list(db.execute(
        select(CollegeAttendanceSnapshot)
        .where(
            CollegeAttendanceSnapshot.organization_id == organization_id,
            CollegeAttendanceSnapshot.student_profile_id.in_(ids) if ids else CollegeAttendanceSnapshot.id.is_(None),
            CollegeAttendanceSnapshot.course_id.is_(None),
        )
        .order_by(CollegeAttendanceSnapshot.student_profile_id, CollegeAttendanceSnapshot.as_of.desc())
    ).scalars())
    attendance = _first_by_student(attendance_rows)
    coding_rows = list(db.execute(
        select(CollegeCodingSnapshot)
        .where(CollegeCodingSnapshot.organization_id == organization_id, CollegeCodingSnapshot.student_profile_id.in_(ids) if ids else CollegeCodingSnapshot.id.is_(None))
        .order_by(CollegeCodingSnapshot.student_profile_id, CollegeCodingSnapshot.captured_at.desc())
    ).scalars())
    coding = _first_by_student(coding_rows)
    careers = {
        row.student_profile_id: row for row in db.execute(select(CollegeCareerProfile).where(
            CollegeCareerProfile.organization_id == organization_id,
            CollegeCareerProfile.student_profile_id.in_(ids) if ids else CollegeCareerProfile.id.is_(None),
        )).scalars()
    }
    placement_outcomes: dict[str, str] = {}
    outcome_priority = {"selected": 1, "offered": 2, "joined": 3}
    if ids:
        for application in db.execute(select(CollegePlacementApplication).where(
            CollegePlacementApplication.organization_id == organization_id,
            CollegePlacementApplication.student_profile_id.in_(ids),
            CollegePlacementApplication.outcome.in_(tuple(outcome_priority)),
        )).scalars():
            current = placement_outcomes.get(application.student_profile_id)
            if current is None or outcome_priority[application.outcome] > outcome_priority[current]:
                placement_outcomes[application.student_profile_id] = application.outcome
    fee_clearance = fee_clearance_by_student(db, organization_id, ids)
    items = []
    for student, client, program, department, cohort in pairs:
        snapshot = readiness.get(student.id)
        rankable = bool(snapshot and snapshot.score is not None and float(snapshot.coverage_percent) >= float(policy.minimum_coverage_percent))
        effective_band = snapshot.band if rankable else "insufficient_evidence"
        term = terms.get(student.id)
        attendance_row = attendance.get(student.id)
        coding_row = coding.get(student.id)
        career = careers.get(student.id)
        placement_outcome = career.placement_status if career else "seeking"
        if placement_outcome not in {"placed", "joined"} and student.id in placement_outcomes:
            placement_outcome = placement_outcomes[student.id]
        items.append({
            "id": student.id,
            "client_id": student.client_id,
            "name": f"{client.first_name} {client.last_name}".strip(),
            "display_name": f"{client.first_name} {client.last_name}".strip(),
            "display_meta": student.admission_number,
            "profile_ref": {"kind": "client", "id": student.client_id, "href": f"/app/clients/{student.client_id}"},
            "admission_number": student.admission_number,
            "roll_number": student.roll_number,
            "semester": student.current_semester,
            "program": {"id": program.id, "name": program.name, "code": program.code},
            "department": {"id": department.id, "name": department.name, "code": department.code},
            "cohort": {
                "id": cohort.id,
                "name": cohort.name,
                "code": cohort.code,
                "section": cohort.section or "General",
                "admission_year": cohort.admission_year,
                "graduation_year": cohort.graduation_year,
            },
            "graduation_year": cohort.graduation_year,
            "section": cohort.section or "General",
            "cgpa": _float(term.cgpa) if term else None,
            "active_backlogs": term.active_backlogs if term else None,
            "attendance_percent": _float(attendance_row.attendance_percent) if attendance_row else None,
            "coding_total": coding_row.total_solved if coding_row else None,
            "coding_fresh_at": coding_row.captured_at.isoformat() if coding_row else None,
            "resume_status": career.resume_status if career else "missing",
            "placement_status": placement_outcome,
            "fee_clearance_status": fee_clearance[student.id]["status"],
            "readiness": serialize_snapshot(snapshot, policy),
            "readiness_band": effective_band,
        })
    next_values = None
    if has_more and pairs:
        student, client, *_ = pairs[-1]
        next_values = {
            "first": client.first_name.casefold(),
            "last": client.last_name.casefold(),
            "id": student.id,
        }
        if sort == "academics_desc":
            term = terms.get(student.id)
            next_values["metric"] = str(term.cgpa if term and term.cgpa is not None else Decimal("-1"))
    return {
        "items": items,
        "total": int(total),
        "limit": page_size,
        "offset": offset if not cursor_values else 0,
        "has_more": has_more,
        "_next_values": next_values,
    }
