"""Public product-demo and custom-project enquiry contracts."""
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import DemoRequest, LegalDocument
from server import app


client = TestClient(app, raise_server_exceptions=True)


def privacy_document_id() -> str:
    with SessionLocal() as db:
        return db.execute(select(LegalDocument.id).where(
            LegalDocument.document_type == "privacy",
            LegalDocument.status == "published",
        )).scalar_one()


def enquiry_body(**overrides) -> dict:
    body = {
        "name": "Kamal Nath",
        "work_email": f"landing-{uuid4().hex[:10]}@example.com",
        "organization_name": "Example College",
        "industry": "college",
        "privacy_document_id": privacy_document_id(),
        "privacy_acknowledged": True,
    }
    body.update(overrides)
    return body


def delete_enquiries(*request_ids: str) -> None:
    with SessionLocal() as db:
        for request_id in request_ids:
            row = db.get(DemoRequest, request_id)
            if row:
                db.delete(row)
        db.commit()


def test_public_site_exposes_the_configured_contact_phone():
    response = client.get("/api/public/site")
    assert response.status_code == 200, response.text
    assert response.json()["contact_phone"] == "+919787867648"


def test_legacy_demo_and_custom_project_enquiries_persist_distinct_types(monkeypatch):
    monkeypatch.setattr("app.api.v1.public_site.send_email", lambda *_args, **_kwargs: True)
    created = []
    try:
        legacy = client.post(
            "/api/public/demo-requests",
            json=enquiry_body(),
            headers={"X-Forwarded-For": f"demo-{uuid4().hex}"},
        )
        assert legacy.status_code == 201, legacy.text
        created.append(legacy.json()["id"])

        project = client.post(
            "/api/public/demo-requests",
            json=enquiry_body(
                inquiry_type="client_project",
                organization_name=None,
                industry="other",
                message="Build a focused operations portal.",
            ),
            headers={"X-Forwarded-For": f"project-{uuid4().hex}"},
        )
        assert project.status_code == 201, project.text
        created.append(project.json()["id"])

        with SessionLocal() as db:
            legacy_row = db.get(DemoRequest, created[0])
            project_row = db.get(DemoRequest, created[1])
            assert legacy_row.inquiry_type == "product_demo"
            assert legacy_row.organization_name == "Example College"
            assert project_row.inquiry_type == "client_project"
            assert project_row.organization_name is None
            assert legacy_row.notified_at is not None and project_row.notified_at is not None
    finally:
        delete_enquiries(*created)


def test_product_demo_still_requires_an_organization():
    response = client.post(
        "/api/public/demo-requests",
        json=enquiry_body(organization_name=None),
        headers={"X-Forwarded-For": f"invalid-{uuid4().hex}"},
    )
    assert response.status_code == 422
    assert "Organization name is required" in response.text
