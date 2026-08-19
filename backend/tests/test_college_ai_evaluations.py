import pytest

from app.ai.access import AccessEnvelope, AccessViolation
from app.ai.catalog import catalog_for
from app.ai.compiler import deterministic_compile
from app.ai.contracts import (
    ConversationReferent, ConversationState, EntityRef, PageContext,
    QueryGoal,
)
from college_ai_evaluations import (
    COLLEGE_QUESTIONS, EVALUATION_ROLES, question_variants,
)


@pytest.fixture(scope="module")
def explicit_context():
    refs = [
        EntityRef(kind="student", id="student-1", label="Asha"),
        EntityRef(kind="student", id="student-2", label="Bala"),
    ]
    return PageContext(
        entity=refs[0],
        selected_entities=refs,
    ), ConversationState(referents=[
        ConversationReferent(ref=ref, source="selection", named=True)
        for ref in refs
    ])


@pytest.mark.parametrize("question", COLLEGE_QUESTIONS)
def test_all_product_questions_compile_to_registered_semantics(question, explicit_context):
    context, state = explicit_context
    catalog = catalog_for("college")

    query = deterministic_compile(
        question, catalog, context=context, state=state,
    )

    assert query is not None
    if query.goal not in {QueryGoal.GENERAL, QueryGoal.CLARIFY}:
        catalog.validate(query)


@pytest.mark.parametrize("question", COLLEGE_QUESTIONS[::10])
def test_paraphrase_and_typo_variants_stay_inside_the_catalog(question, explicit_context):
    context, state = explicit_context
    catalog = catalog_for("college")
    for variant in question_variants(question):
        query = deterministic_compile(
            variant, catalog, context=context, state=state,
        )
        assert query is not None
        if query.goal not in {QueryGoal.GENERAL, QueryGoal.CLARIFY}:
            catalog.validate(query)


@pytest.mark.parametrize("role", EVALUATION_ROLES)
@pytest.mark.parametrize("question", COLLEGE_QUESTIONS)
def test_acceptance_matrix_has_an_explicit_authorization_outcome(role, question, explicit_context):
    context, state = explicit_context
    catalog = catalog_for("college")
    query = deterministic_compile(question, catalog, context=context, state=state)
    envelope = _envelope(role)

    if query.goal in {QueryGoal.GENERAL, QueryGoal.CLARIFY}:
        return
    if role == "missing_module_staff":
        with pytest.raises(AccessViolation):
            envelope.require_query(catalog, query)
    else:
        envelope.require_query(catalog, query)


@pytest.mark.parametrize(("question", "goal", "analysis", "metric"), (
    ("Which department and class does this student belong to?", QueryGoal.PROFILE, None, None),
    ("Which students have shown a sudden drop in attendance?", QueryGoal.TREND, "attendance_drop", None),
    ("Which students have consistently maintained attendance above 90%?", QueryGoal.TREND, "consistent_attendance", None),
    ("Which class has the highest number of students below 75% attendance?", QueryGoal.AGGREGATE, None, "student_count"),
    ("Which subject is students' weakest overall?", QueryGoal.RANK, None, None),
    ("Which subjects show the biggest improvement?", QueryGoal.TREND, "subject_change", None),
    ("Based on our placement data, which students are most likely to succeed in the upcoming placement drives?", QueryGoal.RANK, "explainable_readiness_not_prediction", None),
))
def test_high_risk_phrasings_compile_to_the_governed_operation(
    question, goal, analysis, metric, explicit_context,
):
    context, state = explicit_context
    query = deterministic_compile(
        question, catalog_for("college"), context=context, state=state,
    )
    assert query.goal == goal
    assert query.requested_analysis == analysis
    if metric:
        assert query.metrics == [metric]


def test_deictic_company_requires_an_explicit_company_referent(explicit_context):
    context, state = explicit_context
    query = deterministic_compile(
        "Which students are eligible for this company's drive?",
        catalog_for("college"), context=context, state=state,
    )
    assert query.goal == QueryGoal.CLARIFY
    assert query.requested_analysis == "missing_company_referent"


def _envelope(role: str) -> AccessEnvelope:
    permissions = {
        "ai.use", "college.students.view", "college.academics.view",
        "college.assessments.view", "college.attendance.view",
        "college.readiness.view", "college.coding.view",
        "college.placements.view", "college.students.contact.view",
    }
    if role == "missing_module_staff":
        permissions -= {
            "college.students.view", "college.academics.view",
            "college.assessments.view", "college.attendance.view",
            "college.readiness.view", "college.coding.view",
            "college.placements.view",
        }
    if role == "missing_sensitive_staff":
        permissions.discard("college.students.contact.view")
    unrestricted = role in {"owner", "institution_staff"}
    student_ids = frozenset({"student-1", "student-2"})
    scope = type("Scope", (), {
        "unrestricted": unrestricted,
        "student_ids": student_ids,
    })()
    domains = {
        "students", "academics", "assessments", "attendance", "readiness",
        "coding", "placements", "documents", "clearance",
    }
    return AccessEnvelope(
        organization_id="org-1", user_id=f"user-{role}", industry="college",
        enabled_modules=frozenset({"college"}), permissions=frozenset(permissions),
        owner=role == "owner",
        domain_levels={domain: "manage" if role == "owner" else "view" for domain in domains},
        domain_scopes={domain: scope for domain in domains},
    )
