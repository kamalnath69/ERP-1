from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.services.college_assessments import (
    calculate_score,
    validate_component_definitions,
    validate_metric_values,
)
from app.services.data_exchange import _exchange_code, resource_catalog
from app.api.v1.college_placement import ConnectorBody, SyncBody
from pydantic import ValidationError


def component(
    code: str,
    *,
    maximum: int = 100,
    weightage_bps: int = 0,
    metric_type: str = "number",
    required: bool = True,
) -> dict:
    return {
        "name": code.replace("_", " ").title(),
        "code": code,
        "component_type": "assessment",
        "metric_type": metric_type,
        "max_marks": maximum,
        "weightage_bps": weightage_bps,
        "is_required": required,
        "settings": {},
    }


def snapshot(components: list[dict], method: str, config: dict | None = None) -> dict:
    normalized = validate_component_definitions(components, method, config or {})
    return {
        "components": normalized,
        "calculation_method": method,
        "calculation_config": config or {},
        "final_score_max": 100,
    }


def test_two_internal_college_uses_its_configured_average() -> None:
    scheme = snapshot([component("INTERNAL_1"), component("INTERNAL_2")], "average")

    assert calculate_score(scheme, {"INTERNAL_1": 70, "INTERNAL_2": 90}) == Decimal("80.00")


def test_three_internal_college_can_use_best_two_without_fixed_columns() -> None:
    scheme = snapshot(
        [component("CIA_1"), component("CIA_2"), component("CIA_3")],
        "best_n",
        {"best_n": 2, "minimum_components": 2},
    )

    assert calculate_score(scheme, {"CIA_1": 60, "CIA_2": 80, "CIA_3": 90}) == Decimal("85.00")


def test_weighted_practical_pattern_respects_each_configured_maximum() -> None:
    scheme = snapshot([
        component("THEORY", maximum=100, weightage_bps=7000),
        component("PRACTICAL", maximum=50, weightage_bps=3000),
    ], "weighted_sum")

    assert calculate_score(scheme, {"THEORY": 80, "PRACTICAL": 45}) == Decimal("83.00")


def test_minimum_component_rule_returns_insufficient_evidence_instead_of_zero() -> None:
    scheme = snapshot(
        [component("CIA_1"), component("CIA_2"), component("CIA_3", required=False)],
        "average",
        {"minimum_components": 2},
    )

    assert calculate_score(scheme, {"CIA_1": 74}) is None


def test_custom_coding_metrics_are_typed_and_not_product_constants() -> None:
    scheme = snapshot([
        component("CODING_SCORE", maximum=100, weightage_bps=5000),
        component("SQL_TEST", maximum=50, weightage_bps=3000, metric_type="integer"),
        component("TEST_CASES", maximum=200, weightage_bps=2000, metric_type="count"),
    ], "weighted_sum")

    values = validate_metric_values(
        scheme["components"],
        {"CODING_SCORE": 80, "SQL_TEST": 40, "TEST_CASES": 180},
        allow_partial=False,
    )
    assert values == {"CODING_SCORE": 80.0, "SQL_TEST": 40, "TEST_CASES": 180}
    assert calculate_score(scheme, values) == Decimal("82.00")


def test_unknown_or_out_of_range_metrics_are_rejected() -> None:
    scheme = snapshot([component("INTERNAL")], "average")

    with pytest.raises(ValueError, match="Unknown metrics"):
        calculate_score(scheme, {"PRODUCT_FIXED_COLUMN": 10})
    with pytest.raises(ValueError, match="cannot exceed"):
        calculate_score(scheme, {"INTERNAL": 101})


def test_best_n_must_fit_the_college_component_count() -> None:
    with pytest.raises(HTTPException, match="Best N"):
        snapshot([component("ONLY_INTERNAL")], "best_n", {"best_n": 2})


def test_exchange_codes_are_normalized_for_dynamic_scheme_and_cycle_imports() -> None:
    errors: list[str] = []

    assert _exchange_code(" internal exam - 2 ", "cycle_code", errors, max_length=60) == "INTERNAL_EXAM_2"
    assert errors == []


def test_catalog_hides_write_methods_when_role_cannot_commit_resource() -> None:
    read_only_catalog = resource_catalog({
        "college.imports.manage",
        "college.academics.view",
        "college.assessments.view",
    })
    structure = next(item for item in read_only_catalog if item["key"] == "academic_structure")
    marks = next(item for item in read_only_catalog if item["key"] == "assessment_marks")

    assert structure["methods"] == []
    assert structure["importable"] is False
    assert marks["methods"] == []

    academic_admin_catalog = resource_catalog({
        "college.imports.manage",
        "college.academics.view",
        "college.academics.manage",
    })
    structure = next(item for item in academic_admin_catalog if item["key"] == "academic_structure")
    assert structure["methods"] == ["excel", "csv"]


def test_erp_connector_accepts_dynamic_metric_paths_and_rejects_unknown_resources() -> None:
    connector = ConnectorBody(
        name="College ERP",
        base_url="https://erp.example.edu/api",
        api_key="secret",
        mapping={
            "resources": {
                "assessment_marks": {
                    "path": "/assessment-results",
                    "root_path": "result.items",
                    "fields": {"metrics": "scores"},
                    "metrics": {"CUSTOM_TEST": "scores.custom"},
                },
            },
        },
        pagination={"mode": "cursor", "cursor_param": "cursor", "cursor_path": "meta.next_cursor"},
    )
    assert "assessment_marks" in connector.mapping["resources"]

    with pytest.raises(ValidationError, match="Unsupported ERP resources"):
        ConnectorBody(
            name="College ERP",
            base_url="https://erp.example.edu/api",
            api_key="secret",
            mapping={"resources": {"fixed_internal_exam": {}}},
        )
    with pytest.raises(ValidationError, match="duplicates"):
        SyncBody(resource_types=["students", "students"], idempotency_key="sync-request-1")
