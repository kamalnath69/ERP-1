import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.ai import compiler_v3
from app.ai.capabilities import CapabilitySnapshot, planner_tool_schemas
from app.ai.compiler_v3 import compile_turn, requests_exact_count
from app.ai.document_chunking import chunk_document_pages
from app.ai.execution_v3 import _history_input
from app.ai.grounding_v3 import answer_from_text, evidence_from_trace, verify_answer
from app.ai.local_contracts import IntentMatch
from app.ai.local_intent import normalize_language
from app.ai.personalization import AssistantPreferences
from app.ai.v3_cache import BoundedTTLCache
from app.ai.v3_contracts import AIQueryPlanV2, EvidenceBundleV1
from app.services import ai_metering
from app.services.ai_metering import DEFAULT_AI_CREDIT_POLICY, calculate_charge


GOLDEN_PATH = Path(__file__).with_name("ai_execution_v3_golden_v1.json")


def _fallback_intent(*_args, **_kwargs):
    return IntentMatch(outcome="fallback", confidence=0, reason="unsupported")


def _compile_without_database(monkeypatch, message: str, *, industry: str = "business", context=None):
    monkeypatch.setattr(compiler_v3, "fast_conversation_reply", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(compiler_v3, "interpret_business_query", _fallback_intent)
    user = SimpleNamespace(organization_id="organization-1")
    return compile_turn(
        SimpleNamespace(), user, message, industry=industry, location_id=None,
        context_state=context, explicit_context=None, preferences=AssistantPreferences(),
    )


def test_v3_contracts_reject_unknown_fields():
    with pytest.raises(ValidationError):
        AIQueryPlanV2(extra_policy="unsafe")
    with pytest.raises(ValidationError):
        EvidenceBundleV1(secret="must-not-pass")


def test_planner_schemas_expose_only_authorized_subjects_metrics_and_actions():
    snapshot = CapabilitySnapshot(
        organization_id="organization-1", user_id="user-1", industry="business",
        access_version=3,
        tool_names=["business_records", "business_analytics", "prepare_action"],
        record_subjects=["clients"], record_entity_kinds=["client"],
        analytic_metrics=["clients"], action_names=["create_task"],
    )
    schemas = {schema["name"]: schema for schema in planner_tool_schemas(snapshot)}

    assert schemas["business_records"]["parameters"]["properties"]["subject"]["enum"] == ["clients"]
    assert schemas["business_analytics"]["parameters"]["properties"]["metric"]["enum"] == ["clients"]
    assert schemas["prepare_action"]["parameters"]["properties"]["action_type"]["enum"] == ["create_task"]


def test_planner_entity_schemas_hide_unauthorized_record_kinds():
    snapshot = CapabilitySnapshot(
        organization_id="organization-1", user_id="user-1", industry="business",
        access_version=3, tool_names=["resolve_records", "entity_workspace"],
        record_subjects=["clients"], record_entity_kinds=["client"],
    )
    schemas = {schema["name"]: schema for schema in planner_tool_schemas(snapshot)}

    resolve_kinds = schemas["resolve_records"]["parameters"]["properties"]["kinds"]["items"]["enum"]
    workspace_kinds = schemas["entity_workspace"]["parameters"]["properties"]["kind"]["enum"]
    assert resolve_kinds == ["client"]
    assert workspace_kinds == ["client"]


def test_exact_count_is_requested_only_by_explicit_count_language():
    assert requests_exact_count("How many active clients are there?") is True
    assert requests_exact_count("evlo customers irukaanga") is True
    assert requests_exact_count("List active clients") is False
    assert requests_exact_count("Show more clients") is False
    assert requests_exact_count("Show discounted invoices") is False


def test_planner_history_is_bounded_and_keeps_the_most_recent_context():
    history = [
        SimpleNamespace(role="user", content=f"old-{index} " + ("x" * 2_000))
        for index in range(10)
    ]

    result = _history_input(history)

    assert len(result) <= 8
    assert sum(len(item["content"]) for item in result) <= 8_000
    assert result[-1]["content"].startswith("old-9")
    assert all(len(item["content"]) <= 1_400 for item in result)


def test_single_keyword_cannot_select_a_local_route(monkeypatch):
    result = _compile_without_database(monkeypatch, "item")

    assert result.plan.planner_kind == "model"
    assert result.plan.steps == []
    assert result.plan.synthesis_required is True


def test_compound_request_uses_the_planner_instead_of_a_partial_match(monkeypatch):
    result = _compile_without_database(monkeypatch, "List clients and explain why revenue dropped")

    assert result.plan.planner_kind == "model"
    assert result.plan.operation == "plan"


def test_scoped_follow_up_remains_provider_free(monkeypatch):
    result = _compile_without_database(monkeypatch, "who are they", context={
        "last_read": {
            "tool": "business_records",
            "arguments": {"subject": "clients", "status": "active"},
        },
    })

    assert result.plan.planner_kind == "deterministic"
    assert result.plan.steps[0].arguments == {"subject": "clients", "status": "active", "location_id": None}
    assert result.plan.synthesis_required is False


def test_college_structure_query_never_becomes_a_generic_record_query(monkeypatch):
    result = _compile_without_database(monkeypatch, "Show the 2027 AIML batch", industry="college")

    assert result.plan.planner_kind == "model"
    assert result.plan.domain == "college"


def test_bounded_cache_expires_and_evicts_least_recently_used(monkeypatch):
    now = [10.0]
    monkeypatch.setattr("app.ai.v3_cache.monotonic", lambda: now[0])
    cache = BoundedTTLCache(maxsize=2, ttl_seconds=5)
    cache.set("first", 1)
    cache.set("second", 2)
    assert cache.get("first") == 1
    cache.set("third", 3)

    assert cache.get("second") is None
    assert cache.get("first") == 1
    now[0] = 16.0
    assert cache.get("first") is None
    assert cache.get("third") is None


def test_evidence_bundle_excludes_private_and_ui_payloads():
    bundle = evidence_from_trace([{
        "name": "business_records",
        "result": {
            "count": 1,
            "confirmation_token": "secret-token",
            "payload": {"private": "value"},
            "presentation": {"type": "table"},
            "query_spec": {"subject": "clients"},
            "items": [{
                "id": "client-1",
                "display_name": "Aarav Krishnan",
                "status": "active",
                "pending_paise": 25000,
                "api_key": "secret-key",
                "avatar_base64": "private-image",
            }],
        },
    }])

    rendered = bundle.model_dump_json()
    assert "secret-token" not in rendered
    assert "secret-key" not in rendered
    assert "private-image" not in rendered
    assert "query_spec" not in rendered
    assert "INR 250" in rendered
    assert len(bundle.facts) == 2


def test_grounding_accepts_supported_money_name_status_and_identifier():
    evidence = evidence_from_trace([{
        "name": "business_records",
        "result": {"items": [{
            "id": "sale-1",
            "display_name": "Aarav Krishnan",
            "invoice_number": "DEMO-GYM-0004",
            "status": "partially_paid",
            "pending_paise": 25000,
        }]},
    }])
    answer = answer_from_text(
        "Aarav Krishnan has INR 250 pending on invoice DEMO-GYM-0004, which is partially paid. [E1]"
    )

    outcome = verify_answer(answer, evidence, high_risk=True)

    assert outcome.status == "passed"
    assert outcome.unsupported_claims == []


@pytest.mark.parametrize("claim", [
    "Aarav Krishnan has INR 999 pending. [E1]",
    "Aarav Krishnan is paid. [E1]",
    "Arjun Prakash has INR 250 pending. [E1]",
    "Aarav Krishnan has invoice DEMO-GYM-9999. [E1]",
])
def test_grounding_rejects_invented_facts(claim):
    evidence = evidence_from_trace([{
        "name": "business_records",
        "result": {"items": [{
            "id": "sale-1",
            "display_name": "Aarav Krishnan",
            "invoice_number": "DEMO-GYM-0004",
            "status": "partially_paid",
            "pending_paise": 25000,
        }]},
    }])

    outcome = verify_answer(answer_from_text(claim), evidence, high_risk=True)

    assert outcome.status == "deterministic_fallback"
    assert outcome.unsupported_claims == [claim.rsplit(" [E1]", 1)[0]]


def test_grounding_supports_multiple_evidence_citations_for_comparisons():
    evidence = evidence_from_trace([{
        "name": "college_students",
        "result": {"items": [
            {"id": "cohort-1", "display_name": "ECE 2026", "attendance_percentage": 81},
            {"id": "cohort-2", "display_name": "ECE 2027", "attendance_percentage": 87},
        ]},
    }])
    answer = answer_from_text("ECE 2027 has higher attendance at 87% than ECE 2026 at 81%. [E1, E2]")

    assert answer.claims[0].evidence_ids == ["E1", "E2"]
    assert verify_answer(answer, evidence, high_risk=False).status == "passed"


def test_heading_aware_chunking_preserves_metadata_and_marks_partial_indexes():
    body = " ".join(f"word{index}" for index in range(1800))
    chunks = chunk_document_pages(
        [(3, f"# Attendance Policy\n\n{body}")],
        minimum_tokens=400, maximum_tokens=700, overlap_tokens=80, max_chunks=2,
    )

    assert len(chunks) == 2
    assert all(chunk.page_number == 3 for chunk in chunks)
    assert all(chunk.section == "Attendance Policy" for chunk in chunks)
    assert all(chunk.token_count <= 780 for chunk in chunks)
    assert chunks[-1].partial_index is True


def test_mixed_model_metering_keeps_one_provider_backed_minimum(monkeypatch):
    monkeypatch.setattr(ai_metering, "credit_policy", lambda _db: DEFAULT_AI_CREDIT_POLICY)
    charge = calculate_charge(None, "fallback", {
        "provider_requests": 2,
        "input_tokens": 900,
        "output_tokens": 120,
        "model_usage": {
            "gpt-5.4-mini": {"input_tokens": 500, "cached_input_tokens": 100, "output_tokens": 40},
            "gpt-5.4": {"input_tokens": 400, "cached_input_tokens": 0, "output_tokens": 80},
        },
    })
    local = calculate_charge(None, "database", {
        "provider_requests": 0, "input_tokens": 0, "output_tokens": 0,
    })

    assert charge.credits >= 1
    assert local.credits == 0


def test_versioned_golden_set_covers_required_domains_and_languages():
    fixture = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    cases = fixture["cases"]
    domains = {case["domain"] for case in cases}
    languages = {case["language"] for case in cases}

    assert fixture["version"] == "ai-execution-v3-golden-1"
    assert len(cases) >= 20
    assert {"en", "ta", "tanglish"} <= languages
    assert {
        "conversation", "records", "follow_up", "ambiguity", "finance", "clinical",
        "college_academics", "placements", "documents", "protected_data", "dates",
    } <= domains
    assert all({"id", "prompt", "language", "expected_path", "provider_free"} <= case.keys() for case in cases)


def test_golden_language_classification_is_turn_local_and_precise():
    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))["cases"]

    mismatches = [
        (case["id"], normalize_language(case["prompt"])[1], case["language"])
        for case in cases
        if normalize_language(case["prompt"])[1] != case["language"]
    ]

    assert mismatches == []
