"""Database-free contracts for the public legal and College ERP interfaces."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.api.v1.college_integrations import (
    CredentialBody, PushBatchBody, _extract_prefix, _issue_token, integration_openapi,
)
from app.api.v1.public_site import (
    DemoRequestBody, LegalDraftBody, LegalDraftUpdateBody, LegalProfileBody,
    PublishBody, _enquiry_notification,
)
from app.services.college_imports import normalize_row, validate_row
from app.services.public_site import (
    LEGAL_PROFILE_DEFAULTS, VERSION_TWO_DOCUMENTS,
    content_hash, materialize_legal_content,
)


def test_legal_defaults_do_not_invent_operator_identity_or_jurisdiction():
    assert LEGAL_PROFILE_DEFAULTS["legal_name"] == ""
    assert LEGAL_PROFILE_DEFAULTS["registered_address"] == ""
    assert LEGAL_PROFILE_DEFAULTS["country"] == ""
    assert LEGAL_PROFILE_DEFAULTS["state"] == ""
    assert LEGAL_PROFILE_DEFAULTS["jurisdiction"] == ""
    assert LEGAL_PROFILE_DEFAULTS["contact_phone"] == "+919787867648"


def test_public_enquiry_contract_is_backward_compatible_and_project_aware():
    common = {
        "name": "Kamal Nath",
        "work_email": "kamal@example.com",
        "industry": "other",
        "privacy_document_id": "privacy-1",
        "privacy_acknowledged": True,
    }
    legacy = DemoRequestBody(**common, organization_name="Example College")
    assert legacy.inquiry_type == "product_demo"

    project = DemoRequestBody(**common, inquiry_type="client_project")
    assert project.organization_name is None

    with pytest.raises(ValidationError, match="Organization name is required"):
        DemoRequestBody(**common)


def test_public_contact_phone_and_notification_copy_are_validated():
    profile = LegalProfileBody(
        brand_name="Edvatiq", legal_name="Edvatiq Labs", registered_address="Chennai, Tamil Nadu",
        country="India", state="Tamil Nadu", jurisdiction="Chennai courts",
        support_email="sales@edvatiq.com", contact_phone="+91 97878 67648",
        privacy_email="privacy@edvatiq.com", grievance_contact="Support team",
        version=1,
    )
    assert profile.contact_phone == "+91 97878 67648"

    row = type("Enquiry", (), {
        "inquiry_type": "client_project", "name": "Kamal Nath", "work_email": "kamal@example.com",
        "organization_name": None, "industry": "other", "role": "Founder", "phone": None,
        "message": "Build an internal operations portal.",
    })()
    subject, text, body = _enquiry_notification(row)
    assert subject == "Project enquiry from Kamal Nath"
    assert "Custom software project" in text
    assert "New custom software project enquiry" in body


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


def test_version_two_legal_pack_is_detailed_reviewable_markdown():
    assert set(VERSION_TWO_DOCUMENTS) == {"terms", "privacy", "refund"}

    expected_topics = {
        "terms": ("AI-assisted features", "Acceptable use", "Organization data"),
        "privacy": ("Individual choices and rights", "AI-assisted processing", "Retention"),
        "refund": ("Failed, pending, and reversed payments", "Duplicate payments", "Statutory and consumer rights"),
    }
    hashes = set()
    for kind, document in VERSION_TWO_DOCUMENTS.items():
        content = document["content"].strip()
        assert content.startswith(f"# {document['title']}")
        assert len(content) >= 8_000
        assert content.count("\n## ") >= 15
        assert "{{legal_name}}" in content
        assert "{{support_email}}" in content
        assert not any(marker in content.lower() for marker in ("<script", "<iframe", "javascript:"))
        assert all(topic in content for topic in expected_topics[kind])
        hashes.add(content_hash(content))
    assert len(hashes) == 3


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
    operation = contract["paths"]["/api/integrations/v1/college/{resource}"]["post"]
    assert set(operation["x-edvatiq-resource-schemas"]) == {
        "departments", "programs", "cohorts", "terms", "courses",
        "exam_cycles", "assessment_marks",
    }
    cohort_schema = contract["components"]["schemas"]["CollegeCohortRecord"]
    assert {"program_code", "graduation_year", "section"}.issubset(cohort_schema["properties"])
    marks_schema = contract["components"]["schemas"]["CollegeAssessmentMarksRecord"]
    assert marks_schema["properties"]["metrics"]["additionalProperties"] is True
    assert "cycle_code" in marks_schema["required"]
