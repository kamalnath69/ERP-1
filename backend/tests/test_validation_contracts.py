from pydantic import Field, ValidationError

from fastapi import HTTPException

from app.api.v1.gym import MeasurementBody
from app.api.v1.super_admin import OverrideBody, RechargePackBody, RefundBody
from app.schemas.validation import RequestModel
from app.services.upload_validation import safe_upload_name, validate_upload_signature
from server import _validation_payload


class ExampleWrite(RequestModel):
    name: str = Field(min_length=1, max_length=20)
    optional_note: str | None = None
    password: str


def test_browser_write_models_trim_ordinary_text_and_forbid_unknown_fields():
    value = ExampleWrite(name="  Kavya  ", optional_note="   ", password="  keep spaces  ")
    assert value.name == "Kavya"
    assert value.optional_note is None
    assert value.password == "  keep spaces  "

    try:
        ExampleWrite(name="Kavya", password="secret", unexpected=True)
    except ValidationError as exc:
        assert exc.errors()[0]["type"] == "extra_forbidden"
    else:
        raise AssertionError("unknown fields must be rejected")


def test_super_admin_amounts_and_cross_field_windows_are_authoritative():
    for model, payload in [
        (RechargePackBody, {"name": "Pack", "credits": 0, "price_paise": 100}),
        (RefundBody, {"amount_paise": 0, "reason": "Valid reason", "idempotency_key": "retry-key", "mfa_code": "123456"}),
        (OverrideBody, {
            "feature_code": "module.ai", "value": True, "reason": "Temporary access",
            "starts_at": "2026-08-13T00:00:00Z", "ends_at": "2026-08-12T00:00:00Z", "version": 1,
        }),
    ]:
        try:
            model.model_validate(payload)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"{model.__name__} accepted an invalid payload")


def test_validation_payload_is_field_addressable_and_never_echoes_sensitive_input():
    payload = _validation_payload([{
        "type": "string_too_short",
        "loc": ("body", "password"),
        "msg": "Password is too short",
        "input": "DoNotEchoThisPassword",
        "ctx": {"min_length": 10},
    }])

    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["field_errors"] == {"password": ["Password is too short"]}
    assert "DoNotEchoThisPassword" not in str(payload)
    assert set(payload["detail"][0]) == {"loc", "type", "msg"}


def test_measurements_reject_empty_non_numeric_and_non_finite_values():
    invalid_metrics = [{}, {"weight_kg": "heavy"}, {"weight_kg": float("inf")}, {"": 10}]
    for metrics in invalid_metrics:
        try:
            MeasurementBody(client_id="client-1", metrics=metrics)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"MeasurementBody accepted invalid metrics: {metrics!r}")

    assert MeasurementBody(client_id="client-1", metrics={"weight_kg": 72.5}).metrics["weight_kg"] == 72.5


def test_upload_names_and_signatures_must_match_the_declared_type():
    assert safe_upload_name("../profile.jpeg", "image/jpeg") == "profile.jpeg"
    validate_upload_signature(b"\x89PNG\r\n\x1a\nimage-data", "image/png")

    for action in [
        lambda: safe_upload_name("invoice.exe", "application/pdf"),
        lambda: validate_upload_signature(b"not-a-pdf", "application/pdf"),
        lambda: validate_upload_signature(b"MZexecutable", "text/plain"),
    ]:
        try:
            action()
        except HTTPException as exc:
            assert exc.status_code == 422
        else:
            raise AssertionError("Disguised upload was accepted")
