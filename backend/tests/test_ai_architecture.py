import pytest
from types import SimpleNamespace
from pydantic import ValidationError

from app.ai.actions import ACTION_REGISTRY
from app.ai.contracts import AIResponseV1, ResponseBlock, compose_response
from app.ai.local_intent import interpret_business_query
from app.ai.orchestrator import classify_route, fast_conversation_reply, tool_schemas_for_route
from app.api.v1.ai import _updated_context_state, _without_confirmation_tokens
from app.ai.tools import _academic_match_score, _match_academic_row, _normalize_record_spec, _section_key, _serialize_record
from app.api.v1.college import CohortBody, _cohort_graduation_year


def test_routes_complex_requests_without_model_guesswork():
    assert classify_route("Hi!") == "conversation"
    assert classify_route("Compare this month's revenue trend") == "analytics"
    assert classify_route("What does our cancellation policy say?") == "knowledge"
    assert classify_route("Send a renewal reminder") == "action"
    assert classify_route("How many clients visited today?") == "business"


def test_simple_conversation_is_localized_without_a_model_call():
    assert fast_conversation_reply("Hello!")["language"] == "en"
    assert fast_conversation_reply("Vanakkam")["language"] == "tanglish"
    assert fast_conversation_reply("வணக்கம்")["language"] == "ta"
    assert fast_conversation_reply("Hi, show today's sales") is None


def test_each_ai_route_receives_only_relevant_tools():
    assert {tool["name"] for tool in tool_schemas_for_route("analytics")} == {
        "business_summary", "business_records", "business_analytics", "resolve_records", "entity_workspace",
    }
    assert {tool["name"] for tool in tool_schemas_for_route("knowledge")} == {
        "search_knowledge", "business_records", "client_workspace", "resolve_records", "entity_workspace",
    }
    assert "prepare_action" not in {tool["name"] for tool in tool_schemas_for_route("business")}


def test_college_ai_route_is_evidence_backed_and_read_only():
    assert {tool["name"] for tool in tool_schemas_for_route("college")} == {
        "college_students",
        "college_academic_structure",
        "college_student_intelligence",
        "college_placement_dashboard",
        "college_opportunity_candidates",
        "search_knowledge",
    }
    student_tool = next(tool for tool in tool_schemas_for_route("college") if tool["name"] == "college_students")
    properties = student_tool["parameters"]["properties"]
    assert {"department", "section", "graduation_years", "cohort_ids", "placement_status", "sort"}.issubset(properties)
    assert set(properties["sort"]["enum"]) >= {"name", "academics_desc"}


def test_college_academic_scope_uses_live_codes_and_clarifies_ambiguity():
    body = CohortBody(
        program_id="program-1",
        name="Artificial Intelligence 2027 / A",
        code="AIML-2027-A",
        admission_year=2024,
        section="A",
    )
    assert _cohort_graduation_year(body, SimpleNamespace(duration_semesters=6)) == 2027
    rows = [
        SimpleNamespace(id="aiml", name="Artificial Intelligence and Machine Learning", code="AIML"),
        SimpleNamespace(id="it", name="Information Technology", code="IT"),
        SimpleNamespace(id="mech", name="Mechanical Engineering", code="MECH"),
        SimpleNamespace(id="eee", name="Electrical and Electronics Engineering", code="EEE"),
    ]
    assert _academic_match_score(rows[0], "AIML") == 1.0
    matched, error = _match_academic_row(rows, "Mechanical Engineering", "department")
    assert matched.id == "mech"
    assert error is None

    ambiguous = [
        SimpleNamespace(id="it", name="Information Technology", code="IT"),
        SimpleNamespace(id="industrial", name="Industrial Technology", code="IND-TECH"),
    ]
    matched, error = _match_academic_row(ambiguous, "technology", "department")
    assert matched is None
    assert error["clarification_required"] is True
    assert len(error["options"]) == 2
    assert _section_key("AIML Section A") == "a"


def test_college_batch_language_bypasses_generic_inventory_intent():
    class CollegeDb:
        def get(self, _model, _identifier):
            return SimpleNamespace(
                industry=SimpleNamespace(value="college"),
                timezone="Asia/Kolkata",
            )

    result = interpret_business_query(
        CollegeDb(), SimpleNamespace(organization_id="org-1"), "Show the 2027 batch",
    )
    assert result.outcome == "fallback"
    assert result.reason == "college_structure_requires_college_router"


def test_response_composer_only_emits_approved_blocks():
    response = compose_response("Revenue is improving.", [
        {"name": "business_analytics", "result": {
            "rows": [{"label": "2026-08-01", "value": 120000}],
            "presentation": {"type": "chart", "chart_type": "line", "title": "Revenue", "series": [{"key": "value", "label": "Revenue", "format": "money"}]},
        }},
    ])
    assert response.schema_version == 1
    assert response.blocks[0].type == "chart"
    assert response.blocks[0].data["rows"][0]["value"] == 120000
    with pytest.raises(ValidationError):
        ResponseBlock(id="unsafe", type="raw_html", data={})


def test_action_policy_requires_confirmation_for_messages():
    assert ACTION_REGISTRY["create_task"].risk == "low"
    assert ACTION_REGISTRY["schedule_appointment"].risk == "low"
    assert ACTION_REGISTRY["send_message"].risk == "high"
    assert ACTION_REGISTRY["send_message"].undo is None


def test_confirmation_tokens_are_never_persisted_in_message_payloads():
    value = [{"result": {"action_id": "1", "confirmation_token": "secret", "preview": {"changes": {"name": "A"}}}}]
    sanitized = _without_confirmation_tokens(value)
    assert "confirmation_token" not in sanitized[0]["result"]
    assert sanitized[0]["result"]["action_id"] == "1"


def test_response_contract_rejects_unknown_schema_versions():
    with pytest.raises(ValidationError):
        AIResponseV1(schema_version=2, summary="No", blocks=[])


def test_profile_references_are_normalized_without_arbitrary_urls():
    employee = SimpleNamespace(id="employee-1", first_name="Gopal", last_name="Vaarma", designation="Manager", status="active")
    item = SimpleNamespace(id="item-1", name="Day Pass", sku="PASS-1", item_type="service", price_paise=50000, is_active=True)

    employee_result = _serialize_record(None, None, "employees", employee)
    item_result = _serialize_record(None, None, "catalog", item)

    assert employee_result["profile_ref"] == {"kind": "employee", "id": "employee-1"}
    assert item_result["profile_ref"] == {"kind": "catalog", "id": "item-1"}
    assert "url" not in employee_result["profile_ref"]


def test_entity_kind_is_preserved_for_deterministic_cards():
    response = compose_response("One employee found.", [{
        "name": "business_records",
        "result": {
            "count": 1,
            "items": [{"id": "employee-1", "profile_ref": {"kind": "employee", "id": "employee-1"}}],
            "presentation": {"display": "cards", "title": "Employees", "entity_kind": "employee"},
        },
    }])
    assert response.blocks[0].type == "entity_cards"
    assert response.blocks[0].data["entity_kind"] == "employee"


def test_follow_up_context_preserves_order_without_guessing_ambiguous_records():
    first = {"kind": "client", "id": "client-1", "display_name": "Kavin Raj"}
    second = {"kind": "client", "id": "client-2", "display_name": "Kavin Raj"}
    ambiguous = {"tool_calls": [{
        "name": "resolve_records", "arguments": {"reference": "Kavin Raj"},
        "result": {"resolution": "ambiguous", "items": [first, second]},
    }]}

    state = _updated_context_state({}, ambiguous)

    assert state["recent_entities"] == [first, second]
    assert state.get("primary_entity") is None

    focused = _updated_context_state(state, {"tool_calls": [{
        "name": "entity_workspace", "arguments": {"kind": "client", "id": "client-2"},
        "result": {"record": second},
    }]})
    assert focused["primary_entity"] == {"kind": "client", "id": "client-2"}


def test_follow_up_context_keeps_live_query_definition_not_result_data():
    state = _updated_context_state({}, {"tool_calls": [{
        "name": "business_records",
        "arguments": {"subject": "sales", "days": 30, "location_id": "location-1", "query": "overdue"},
        "result": {"items": []},
    }]})

    assert state["date_range"] == {"days": 30}
    assert state["location_id"] == "location-1"
    assert state["filters"] == {"subject": "sales", "query": "overdue"}
    assert "items" not in state


def test_college_page_scope_is_preserved_without_becoming_a_business_entity():
    scope = {
        "kind": "college_scope",
        "id": "graduation:2027",
        "display_name": "2027 batch",
        "graduation_year": 2027,
        "department_id": None,
        "program_id": None,
        "cohort_id": None,
        "cohort_ids": [],
    }

    state = _updated_context_state({}, {"tool_calls": []}, scope)

    assert state["college_scope"] == scope
    assert state.get("primary_entity") is None
    assert state["recent_entities"] == []


def test_client_record_arguments_are_normalized_before_querying():
    client_spec = _normalize_record_spec(
        "clients", query="all clients", location_id="location-1", days=365,
    )
    purchase_spec = _normalize_record_spec(
        "clients", query="clients who purchased anything / has sales / bought products",
        location_id="location-1", days=365,
    )

    assert client_spec == {
        "subject": "clients", "query": None, "location_id": "location-1", "days": None,
        "status": "all", "created_within_days": None,
    }
    assert purchase_spec == {
        "subject": "purchases", "query": None, "location_id": "location-1", "days": 365,
        "status": None, "created_within_days": None,
    }
