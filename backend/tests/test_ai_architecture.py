import asyncio
import json
import random
from types import SimpleNamespace

import pytest

from app.ai.access import AccessEnvelope, AccessViolation
from app.ai.catalog import CatalogError, catalog_for
from app.ai.compiler import compile_query, deterministic_compile
from app.ai.contracts import (
    Artifact, AssistantInteraction, AssistantOutcome, AssistantRequest,
    AssistantResponse, ConversationReferent,
    ConversationState, EntityRef, FilterOperator, PageContext, QueryFilter,
    QueryGoal, QuerySort, SemanticQuery,
)
from app.ai.definitions import validate_definitions
from app.ai.domains.common import security
from app.ai.engine import _resume_selection
from app.ai.provider import ProviderResponse
from app.api.v1.ai import (
    _authorized_message_dict, _history_query_allowed, _run_query_page,
    _security_allowed,
)


def compile_college(message, *, state=None, context=None):
    return deterministic_compile(
        message,
        catalog_for("college"),
        context=context,
        state=state or ConversationState(),
    )


def test_named_entity_profile_does_not_reuse_a_stale_student():
    state = ConversationState(referents=[ConversationReferent(
        ref=EntityRef(kind="student", id="old-id", label="Lokesh Menon"),
        source="result",
        named=True,
    )])

    query = compile_college("Who is Kamal Raj?", state=state)

    assert query.goal == QueryGoal.PROFILE
    assert query.entities == [EntityRef(kind="student", label="Kamal Raj")]


def test_new_population_question_does_not_inherit_person_context():
    state = ConversationState(referents=[ConversationReferent(
        ref=EntityRef(kind="student", id="student-1", label="Lokesh Menon"),
        source="result",
        named=True,
    )])

    query = compile_college("Tell me about the overall good student", state=state)

    assert query.goal == QueryGoal.RANK
    assert query.entities == []
    assert query.qualitative_definition == "overall_good_student"
    assert query.sort == [QuerySort(field="readiness_score", direction="desc")]


def test_year_scoped_overall_student_is_a_population_not_a_person_name():
    query = compile_college("Tell me about the overall good student of 2026")

    assert query.goal == QueryGoal.RANK
    assert query.entities == []
    assert QueryFilter(
        field="graduation_year", operator=FilterOperator.EQ, value=2026,
    ) in query.filters


def test_complete_profile_requests_governed_history_and_offer_details():
    context = PageContext(entity=EntityRef(kind="student", id="student-1", label="Asha"))

    query = compile_college("Show me the complete profile of this student", context=context)

    assert {"academic_history", "attendance_history", "offers"} <= set(query.fields)


def test_subject_history_language_uses_specialized_governed_analyses():
    weak = compile_college("Which students are consistently weak in core subjects?")
    improved = compile_college("Which students improved the most in their difficult subjects?")

    assert weak.requested_analysis == "consistent_core_subject_weakness"
    assert improved.requested_analysis == "difficult_subject_improvement"
    catalog_for("college").validate(weak)
    catalog_for("college").validate(improved)


def test_high_package_eligibility_filters_opportunities_not_historical_offers():
    query = compile_college(
        "Which unplaced students are eligible for packages at least INR 10 LPA?",
    )

    assert QueryFilter(
        field="opportunity_package_max",
        operator=FilterOperator.GTE,
        value=100_000_000,
    ) in query.filters
    assert not any(item.field == "highest_package" for item in query.filters)


def test_undefined_profile_adjectives_require_explicit_thresholds():
    query = compile_college(
        "Which students have average CGPA but strong placement performance?",
    )

    assert query.goal == QueryGoal.CLARIFY
    assert query.requested_analysis == "undefined_student_profile_thresholds"


def test_safe_general_question_is_not_silently_converted_to_student_search():
    assert compile_college("How does machine learning work?") is None


def test_deictic_student_uses_only_explicit_page_or_ordered_referent():
    context = PageContext(entity=EntityRef(kind="student", id="student-2", label="Asha"))

    query = compile_college("What is this student's current CGPA?", context=context)

    assert query.entities[0].id == "student-2"
    assert "cgpa" in query.fields


def test_ambiguous_best_requires_a_governed_measure():
    query = compile_college("Who is best?")

    assert query.goal == QueryGoal.CLARIFY
    assert query.requested_analysis == "ambiguous_best"


def test_governed_clarification_remains_authorized_in_history():
    query = SemanticQuery(
        goal=QueryGoal.CLARIFY,
        entity="student",
        fields=["id", "name", "cgpa"],
        filters=[QueryFilter(
            field="graduation_year", operator=FilterOperator.EQ, value=2026,
        )],
        sort=[QuerySort(field="cgpa", direction="desc")],
        limit=5,
        requested_analysis="ambiguous_best",
    )

    assert _history_query_allowed(
        _college_envelope({"student-1"}), query.model_dump(mode="json"),
    )


def test_entity_selection_resumes_original_query_without_a_synthetic_prompt():
    query = SemanticQuery(
        goal=QueryGoal.PROFILE,
        entity="student",
        fields=["id", "name", "cgpa"],
        entities=[EntityRef(kind="student", label="Kamal")],
    )
    state = ConversationState(pending_clarification={
        "id": "clarify-1",
        "query": query.model_dump(mode="json"),
        "message": "What is Kamal's CGPA?",
        "entity_ids": ["student-7"],
    })
    request = AssistantRequest(interaction=AssistantInteraction(
        type="select_entity",
        clarification_id="clarify-1",
        entity=EntityRef(kind="student", id="student-7", label="Kamal Raj"),
    ))

    resumed, original_message = _resume_selection(request, state)

    assert resumed.entities[0].id == "student-7"
    assert original_message == "What is Kamal's CGPA?"


def test_catalog_rejects_unregistered_and_non_analytical_fields():
    catalog = catalog_for("college")
    with pytest.raises(CatalogError):
        catalog.validate(SemanticQuery(
            goal=QueryGoal.LIST,
            entity="student",
            fields=["password_hash"],
        ))
    with pytest.raises(CatalogError):
        catalog.validate(SemanticQuery(
            goal=QueryGoal.RANK,
            entity="student",
            fields=["email"],
            sort=[QuerySort(field="email", direction="asc")],
        ))
    with pytest.raises(CatalogError):
        catalog.validate(SemanticQuery(
            goal=QueryGoal.ANALYZE,
            entity="student",
            fields=["id", "name"],
            requested_analysis="model_invented_analysis",
        ))


def test_semantic_definitions_accept_only_safe_registered_values():
    values = validate_definitions({"high_cgpa": 8.5})
    assert values["high_cgpa"] == 8.5
    with pytest.raises(ValueError):
        validate_definitions({"custom_sql": "select * from users"})
    with pytest.raises(ValueError):
        validate_definitions({"low_attendance_percent": "75 OR TRUE"})


def test_data_turn_uses_one_strict_catalog_compilation_call():
    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def respond(self, **kwargs):
            self.calls.append(kwargs)
            arguments = {
                "goal": "list", "entity": "student",
                "fields": ["id", "name", "cgpa"], "metrics": [],
                "filters": [{"field": "cgpa", "operator": "gt", "value": 8}],
                "group_by": [], "sort": [], "entities": [],
                "time_window": None, "limit": 25,
                "qualitative_definition": None, "requested_analysis": None,
            }
            return ProviderResponse(
                output=[{
                    "type": "function_call", "name": "submit_semantic_query",
                    "arguments": json.dumps(arguments),
                }],
                text="", input_tokens=100, output_tokens=30,
            )

    provider = FakeProvider()
    result = asyncio.run(compile_query(
        message="Show students with CGPA above 8",
        catalog=catalog_for("college"), context=None,
        state=ConversationState(), definitions={"high_cgpa": 8.0},
        provider=provider, model="test-model",
    ))

    assert result.provider is not None
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call["parallel_tool_calls"] is False
    assert call["tool_choice"] == {"type": "function", "name": "submit_semantic_query"}
    assert len(call["tools"]) == 1
    assert call["tools"][0]["strict"] is True
    assert "student_department" in call["tools"][0]["parameters"]["properties"]["filters"]["items"]["properties"]["field"]["enum"]


def test_reduced_domain_scope_never_increases_student_reach():
    population = [f"student-{index}" for index in range(80)]
    rng = random.Random(20260817)
    for _ in range(100):
        broad = set(rng.sample(population, rng.randint(0, len(population))))
        narrow = set(rng.sample(sorted(broad), rng.randint(0, len(broad))))
        broad_envelope = _college_envelope(broad)
        narrow_envelope = _college_envelope(narrow)

        broad_scope = broad_envelope.student_scope({"assessments", "placements"})
        narrow_scope = narrow_envelope.student_scope({"assessments", "placements"})
        broad_result = set(population) if broad_scope is None else broad_scope
        narrow_result = set(population) if narrow_scope is None else narrow_scope

        assert narrow_result <= broad_result


def test_typed_security_refs_reauthorize_every_nested_student():
    envelope = _college_envelope({"student-1"})
    label = security(
        permissions=("college.students.view", "college.placements.view"),
        domains=("students", "placements"),
        entity_refs=(
            {"kind": "company", "id": "company-1", "label": "Example Ltd"},
            {"kind": "student", "id": "student-1", "label": "Asha"},
            {"kind": "student", "id": "student-2", "label": "Bala"},
        ),
    )

    assert not _security_allowed(envelope, label.model_dump(mode="json"), "company")


def _college_envelope(
    student_ids, permissions=None, *, owner=False, policy_version=0,
):
    scope = SimpleNamespace(
        unrestricted=owner, student_ids=frozenset(student_ids),
    )
    domains = {
        "students", "academics", "assessments", "attendance", "readiness",
        "coding", "placements", "documents", "clearance",
    }
    return AccessEnvelope(
        organization_id="org-1",
        user_id="user-1",
        industry="college",
        enabled_modules=frozenset({"college"}),
        permissions=frozenset(permissions or {
            "ai.use", "college.students.view", "college.assessments.view",
            "college.placements.view",
        }),
        owner=owner,
        policy_version=policy_version,
        domain_levels={domain: "manage" if owner else "view" for domain in domains},
        domain_scopes={domain: scope for domain in domains},
    )


def test_reduced_permissions_never_unlock_fields_or_aggregates():
    catalog = catalog_for("college")
    population = {"student-1", "student-2"}
    permission_by_field = {
        "cgpa": "college.assessments.view",
        "attendance_percent": "college.attendance.view",
        "readiness_score": "college.readiness.view",
        "email": "college.students.contact.view",
    }
    metric_names = ["average_cgpa", "average_attendance", "readiness_score"]
    rng = random.Random(20260818)
    base = {"ai.use", "college.students.view"}
    optional = set(permission_by_field.values())

    for _ in range(100):
        broad_optional = set(rng.sample(sorted(optional), rng.randint(0, len(optional))))
        narrow_optional = set(rng.sample(sorted(broad_optional), rng.randint(0, len(broad_optional))))
        broad = _college_envelope(population, base | broad_optional)
        narrow = _college_envelope(population, base | narrow_optional)
        query = SemanticQuery(
            goal=QueryGoal.PROFILE, entity="student",
            fields=["id", "name", *permission_by_field],
        )
        broad_fields, _ = broad.projectable_fields(catalog, query)
        narrow_fields, _ = narrow.projectable_fields(catalog, query)
        assert set(narrow_fields) <= set(broad_fields)
        narrow_history = _history_query_allowed(narrow, query.model_dump(mode="json"))
        broad_history = _history_query_allowed(broad, query.model_dump(mode="json"))
        assert not narrow_history or broad_history

        def available_metrics(envelope):
            available = set()
            for metric in metric_names:
                candidate = SemanticQuery(
                    goal=QueryGoal.AGGREGATE, entity="student", metrics=[metric],
                )
                try:
                    envelope.require_query(catalog, candidate)
                except AccessViolation:
                    continue
                available.add(metric)
            return available

        assert available_metrics(narrow) <= available_metrics(broad)


def test_reduced_scope_never_unlocks_history_or_suggestions():
    population = [f"student-{index}" for index in range(50)]
    rng = random.Random(20260819)
    for _ in range(100):
        broad_ids = set(rng.sample(population, rng.randint(0, len(population))))
        narrow_ids = set(rng.sample(sorted(broad_ids), rng.randint(0, len(broad_ids))))
        labelled_ids = set(rng.sample(population, rng.randint(0, min(8, len(population)))))
        label = security(
            domains=("students", "assessments"),
            entity_refs=(
                {"kind": "student", "id": student_id, "label": student_id}
                for student_id in labelled_ids
            ),
        ).model_dump(mode="json")
        broad_allowed = _security_allowed(_college_envelope(broad_ids), label, "student")
        narrow_allowed = _security_allowed(_college_envelope(narrow_ids), label, "student")
        assert not narrow_allowed or broad_allowed


def test_access_version_change_hides_aggregate_history_without_artifacts(monkeypatch):
    permissions = {
        "ai.use", "college.students.view", "college.attendance.view",
    }
    envelope = _college_envelope({"student-1"}, permissions)
    monkeypatch.setattr("app.api.v1.ai.resolve_access_envelope", lambda *_args, **_kwargs: envelope)
    query = SemanticQuery(
        goal=QueryGoal.AGGREGATE, entity="student", metrics=["average_attendance"],
    )
    message = SimpleNamespace(
        id="message-1", conversation_id="conversation-1", turn_id="turn-1",
        role="assistant", content="Average attendance is 92%.", outcome="success",
        artifacts=[], suggestions=[], evidence=[{"facts": {"average": 92}}],
        scope={}, semantic_query=query.model_dump(mode="json"), created_at=None,
        meta={"access_version": 1, "policy_version": envelope.policy_version},
    )

    result = _authorized_message_dict(
        None, SimpleNamespace(access_version=2), message,
    )

    assert result["outcome"] == "access_limited"
    assert result["evidence"] == []
    assert "no longer available" in result["content"]


def test_owner_version_change_reauthorizes_instead_of_hiding_history(monkeypatch):
    permissions = {
        "ai.use", "college.students.view", "college.attendance.view",
    }
    envelope = _college_envelope(
        set(), permissions, owner=True, policy_version=3,
    )
    monkeypatch.setattr(
        "app.api.v1.ai.resolve_access_envelope", lambda *_args, **_kwargs: envelope,
    )
    query = SemanticQuery(
        goal=QueryGoal.AGGREGATE,
        entity="student",
        metrics=["average_attendance"],
    )
    message = SimpleNamespace(
        id="message-1", conversation_id="conversation-1", turn_id="turn-1",
        role="assistant", content="Average attendance is 92%.", outcome="success",
        artifacts=[], suggestions=[], evidence=[{"facts": {"average": 92}}],
        scope={}, semantic_query=query.model_dump(mode="json"), created_at=None,
        meta={"access_version": 1, "policy_version": 2},
    )

    result = _authorized_message_dict(
        None, SimpleNamespace(access_version=2), message,
    )

    assert result["outcome"] == "success"
    assert result["content"] == "Average attendance is 92%."


def test_authorized_history_redacts_internal_ids_from_visible_text(monkeypatch):
    envelope = _college_envelope({"student-1"})
    monkeypatch.setattr("app.api.v1.ai.resolve_access_envelope", lambda *_args, **_kwargs: envelope)
    internal_id = "f94d1b70-cf8e-42e4-8177-6781a6de3602"
    query = SemanticQuery(
        goal=QueryGoal.LIST, entity="student", fields=["id", "name"],
    )
    message = SimpleNamespace(
        id="message-1", conversation_id="conversation-1", turn_id="turn-1",
        role="assistant", content=f"Internal record {internal_id}", outcome="success",
        artifacts=[], suggestions=[{
            "id": "suggestion-1",
            "label": f"Open {internal_id}",
            "prompt": f"Show {internal_id}",
            "security": security(permissions=("ai.use",)).model_dump(mode="json"),
        }], evidence=[], scope={}, semantic_query=query.model_dump(mode="json"),
        created_at=None,
        meta={"access_version": 1, "policy_version": envelope.policy_version},
    )

    result = _authorized_message_dict(
        None, SimpleNamespace(access_version=1), message,
    )

    assert internal_id not in json.dumps(result)


def test_result_pages_execute_again_with_the_current_envelope(monkeypatch):
    envelope = _college_envelope({"student-1"})
    captured = {}
    monkeypatch.setattr("app.api.v1.ai.resolve_access_envelope", lambda *_args, **_kwargs: envelope)

    def execute(_db, _user, query, _catalog, current, *, offset=0):
        captured.update({"envelope": current, "offset": offset, "query": query})
        return AssistantResponse(
            outcome=AssistantOutcome.SUCCESS, answer="One authorized student.",
            artifacts=[Artifact(
                id="artifact-1", type="records",
                data={"items": [{"id": "student-1", "name": "Asha"}], "total": 1},
            )],
        )

    monkeypatch.setattr("app.api.v1.ai.execute_semantic_query", execute)
    query = SemanticQuery(
        goal=QueryGoal.LIST, entity="student", fields=["id", "name"],
    )

    result = _run_query_page(
        None, SimpleNamespace(organization_id="org-1"),
        query.model_dump(mode="json"), "records", None, 25,
    )

    assert captured["envelope"] is envelope
    assert result["items"] == [{"name": "Asha"}]
    assert result["presentation"]["layout"] == "cards"
    assert all(field["key"] != "id" for field in result["presentation"]["fields"])


def test_analytical_filter_requires_an_approved_catalog_field():
    catalog = catalog_for("college")
    query = SemanticQuery(
        goal=QueryGoal.LIST,
        entity="student",
        fields=["id", "name", "cgpa"],
        filters=[QueryFilter(field="cgpa", operator=FilterOperator.GT, value=8)],
    )

    assert catalog.validate(query) is query
