"""Database-free contracts for the public legal and College ERP interfaces."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.api.v1.college_integrations import (
    CredentialBody, PushBatchBody, _extract_prefix, _issue_token, integration_openapi,
)
from app.api.v1.public_site import LegalDraftBody, LegalDraftUpdateBody, PublishBody
from app.services.college_imports import normalize_row, validate_row
from app.services.public_site import LEGAL_PROFILE_DEFAULTS, content_hash, materialize_legal_content


def test_legal_defaults_do_not_invent_operator_identity_or_jurisdiction():
    assert LEGAL_PROFILE_DEFAULTS["legal_name"] == ""
    assert LEGAL_PROFILE_DEFAULTS["registered_address"] == ""
    assert LEGAL_PROFILE_DEFAULTS["country"] == ""
    assert LEGAL_PROFILE_DEFAULTS["state"] == ""
    assert LEGAL_PROFILE_DEFAULTS["jurisdiction"] == ""


def test_legal_markdown_is_html_free_version_locked_and_hashable():
    content = "# Terms\n\n" + "Reviewed policy content. " * 8 + "Contact {{support_email}}."
    draft = LegalDraftUpdateBody(
        title="Terms of Service",
        content_markdown=content,
        version_lock=3,
    )
    rendered = materialize_legal_content(draft.content_markdown, {"support_email": "legal@example.com"})
    assert "legal@example.com" in rendered
    assert len(content_hash(rendered)) == 64
    assert PublishBody(version_lock=3).version_lock == 3

    with pytest.raises(ValidationError):
        LegalDraftBody(title="Terms", content_markdown="<script>alert(1)</script>" + "x" * 100)


def test_push_credentials_are_scoped_expiring_and_never_return_a_recoverable_hash():
    expiry = datetime.now(timezone.utc) + timedelta(days=90)
    body = CredentialBody(
        name="Production student sync",
        scopes=["students", "students", "internship_clearance"],
        expires_at=expiry,
    )
    assert body.scopes == ["students", "internship_clearance"]

    token, prefix, token_hash = _issue_token()
    assert token.startswith("edv_college_")
    assert _extract_prefix(token) == prefix
    assert token not in token_hash and len(token_hash) == 64
    assert _extract_prefix("not-a-credential") is None

    with pytest.raises(ValidationError):
        CredentialBody(name="ERP", scopes=["students"], expires_at=datetime.now(timezone.utc))


def test_push_batch_limit_and_clearance_minimization_are_authoritative():
    with pytest.raises(ValidationError):
        PushBatchBody(records=[{"external_id": str(index)} for index in range(501)])

    normalized = normalize_row({
        "external_id": "clearance-1",
        "admission_number": "CSE-001",
        "status": "cleared",
        "source_updated_at": "2026-08-12T12:00:00Z",
        "outstanding_paise": 500000,
    }, "internship_clearance", {})
    validated, errors = validate_row(normalized, "internship_clearance")
    assert not errors
    assert validated["status"] == "cleared"
    assert "outstanding_paise" not in validated

    invalid, errors = validate_row({**normalized, "status": "paid"}, "internship_clearance")
    assert invalid["status"] == "paid"
    assert errors == ["status must be cleared, pending, or needs_review"]


def test_filtered_openapi_exposes_only_supported_integration_routes():
    contract = integration_openapi()
    assert contract["openapi"].startswith("3.")
    assert "/api/integrations/v1/college/{resource}" in contract["paths"]
    assert "/api/integrations/v1/college/runs/{run_id}" in contract["paths"]
    assert all("super-admin" not in path and "/auth/" not in path for path in contract["paths"])
