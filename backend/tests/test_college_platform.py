"""End-to-end coverage for the College industry workspace."""
from uuid import uuid4
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.ai.fast_queries import _summary_text
from app.ai.tools import tool_college_students
from app.core.config import settings
from app.core.database import SessionLocal
from app.db.seed import ensure_missing_business_roles, ensure_permissions, sync_granular_role_permissions
from app.models import (
    AuditLog, CollegeApplicationStageEvent, CollegeCareerEvidence, CollegeDataConnector,
    CollegeDepartment, CollegeStudentProfile, Organization, Permission, Role,
    RolePermission, User,
)
from app.services.college_access import CollegeAccess
from app.services.college_imports import commit_run, stage_rows
from app.services.college_placement import evaluate_eligibility
from app.services.college_jobs import _public_host, _url_origin
from conftest import delete_signup_challenge, verified_signup_body
from server import app


client = TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def college_account():
    unique = uuid4().hex[:10]
    slug = f"test-college-{unique}"
    email = f"owner-{unique}@example.com"
    created_id = None
    body, challenge_id = verified_signup_body(client, {
        "organization_name": f"Test College {unique}",
        "organization_slug": slug,
        "industry": "college",
        "admin_email": email,
        "admin_password": "Testing@123",
        "admin_first_name": "Test",
        "admin_last_name": "Owner",
        "location_name": "Main Campus",
        "city": "Chennai",
    })
    try:
        response = client.post("/api/auth/register", json=body)
    finally:
        delete_signup_challenge(challenge_id)
    assert response.status_code == 201, response.text
    with SessionLocal() as db:
        organization = db.execute(select(Organization).where(Organization.slug == slug)).scalar_one()
        created_id = organization.id

    login = client.post("/api/auth/login", json={
        "email": email,
        "password": "Testing@123",
        "org_slug": slug,
    })
    assert login.status_code == 200, login.text
    token = login.cookies.get(settings.ACCESS_COOKIE_NAME)
    headers = {"Authorization": f"Bearer {token}"}
    context = client.get("/api/organization/context", headers=headers)
    assert context.status_code == 200, context.text

    with SessionLocal() as db:
        roles = set(db.execute(select(Role.slug).where(Role.organization_id == created_id)).scalars())
        assert {"owner", "academic-admin", "faculty", "admissions"}.issubset(roles)
        owner_permissions = set(db.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .where(Role.organization_id == created_id, Role.slug == "owner")
        ).scalars())
        assert "college.academics.manage" in owner_permissions

    yield headers, context.json(), created_id

    if created_id:
        with SessionLocal() as db:
            db.execute(delete(Organization).where(Organization.id == created_id))
            db.commit()


def _post(path, headers, payload, expected=201):
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code == expected, response.text
    return response.json()


def test_college_academic_structure_lifecycle_bulk_and_multi_cohort_scope(college_account):
    headers, context, organization_id = college_account
    location_id = context["locations"][0]["id"]
    department = _post("/api/college/departments", headers, {
        "name": "Artificial Intelligence and Machine Learning",
        "code": "AIML",
        "location_id": location_id,
    })
    program = _post("/api/college/programs", headers, {
        "department_id": department["id"],
        "name": "B.Tech Artificial Intelligence",
        "code": "BTECH-AIML",
        "degree_type": "undergraduate",
        "duration_semesters": 8,
    })
    bulk_body = {
        "program_id": program["id"],
        "admission_year": 2023,
        "graduation_year": 2027,
        "current_semester": 7,
        "sections": ["a", " B "],
        "idempotency_key": "academic-bulk-aiml-2027",
    }
    bulk = _post("/api/college/cohorts/bulk", headers, bulk_body)
    assert [row["section"] for row in bulk["items"]] == ["A", "B"]
    replay = _post("/api/college/cohorts/bulk", headers, bulk_body)
    assert replay["replayed"] is True
    changed_replay = client.post("/api/college/cohorts/bulk", headers=headers, json={
        **bulk_body, "sections": ["A", "C"],
    })
    assert changed_replay.status_code == 409

    stale_update = client.patch(f"/api/college/departments/{department['id']}", headers=headers, json={
        "version": department["version"] + 1,
        "name": "School of AI",
    })
    assert stale_update.status_code == 409
    updated_department = client.patch(
        f"/api/college/departments/{department['id']}", headers=headers,
        json={"version": department["version"], "name": "School of AI", "reason": "Academic council update"},
    )
    assert updated_department.status_code == 200, updated_department.text
    assert updated_department.json()["version"] == department["version"] + 1

    blocked_program = client.post(f"/api/college/programs/{program['id']}/archive", headers=headers, json={
        "version": program["version"], "reason": "Lifecycle test",
    })
    assert blocked_program.status_code == 409

    section_a, section_b = bulk["items"]
    general = _post("/api/college/cohorts", headers, {
        "program_id": program["id"],
        "name": "Artificial Intelligence 2028",
        "code": "AIML-2028",
        "admission_year": 2024,
        "graduation_year": 2028,
        "current_semester": 5,
        "section": "",
    })
    assert general["section"] == "GENERAL"

    def admit(number, first_name, cohort):
        return _post("/api/college/students", headers, {
            "first_name": first_name,
            "last_name": "Student",
            "email": f"{number.lower()}@example.edu",
            "home_location_id": location_id,
            "admission_number": number,
            "program_id": program["id"],
            "cohort_id": cohort["id"],
            "current_semester": cohort["current_semester"],
            "admitted_on": "2024-07-01",
        })

    first = admit("ADM-AIML-001", "Anika", section_a)
    second = admit("ADM-AIML-002", "Bharat", general)
    blocked_cohort = client.post(f"/api/college/cohorts/{section_a['id']}/archive", headers=headers, json={
        "version": section_a["version"], "reason": "Contains an active student",
    })
    assert blocked_cohort.status_code == 409
    archived = client.post(f"/api/college/cohorts/{section_b['id']}/archive", headers=headers, json={
        "version": section_b["version"], "reason": "Section was not opened",
    })
    assert archived.status_code == 200, archived.text
    restored = client.post(f"/api/college/cohorts/{section_b['id']}/restore", headers=headers, json={
        "version": archived.json()["version"], "reason": "Admissions reopened",
    })
    assert restored.status_code == 200, restored.text

    cohort_params = [
        ("cohort_ids", section_a["id"]),
        ("cohort_ids", general["id"]),
        ("limit", "25"),
    ]
    students = client.get("/api/college/student-intelligence", headers=headers, params=cohort_params)
    assert students.status_code == 200, students.text
    assert {row["id"] for row in students.json()["items"]} == {first["id"], second["id"]}
    dashboard = client.get("/api/college/placement-dashboard", headers=headers, params=cohort_params[:2])
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["metrics"]["participating_students"] == 2

    with SessionLocal() as db:
        grants = {
            row.slug: set(db.execute(
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == row.id)
            ).scalars())
            for row in db.execute(select(Role).where(
                Role.organization_id == organization_id,
                Role.slug.in_(("principal", "academic-admin")),
            )).scalars()
        }
        assert "college.academics.view" in grants["principal"]
        assert "college.academics.manage" not in grants["principal"]
        assert "college.academics.manage" in grants["academic-admin"]
        archive_audit = db.execute(select(AuditLog).where(
            AuditLog.organization_id == organization_id,
            AuditLog.action == "college.cohort.archive",
            AuditLog.resource_id == section_b["id"],
        )).scalar_one()
        assert archive_audit.meta["changes"]["reason"] == "Section was not opened"


def test_enterprise_policy_scopes_hod_data_fields_dashboard_and_finance(college_account):
    owner_headers, context, organization_id = college_account
    location_id = context["locations"][0]["id"]

    def structure(code, name):
        department = _post("/api/college/departments", owner_headers, {
            "name": name, "code": code, "location_id": location_id,
        })
        program = _post("/api/college/programs", owner_headers, {
            "department_id": department["id"], "name": f"B.E. {name}",
            "code": f"BE-{code}", "degree_type": "undergraduate", "duration_semesters": 8,
        })
        return department, program

    ece, ece_program = structure("ECE", "Electronics and Communication Engineering")
    _cse, cse_program = structure("CSE", "Computer Science Engineering")

    def cohort(program, code, section):
        return _post("/api/college/cohorts", owner_headers, {
            "program_id": program["id"], "name": f"{code} 2027 {section}",
            "code": f"{code}-2027-{section}", "admission_year": 2023,
            "graduation_year": 2027, "current_semester": 7, "section": section,
        })

    ece_a = cohort(ece_program, "ECE", "A")
    ece_b = cohort(ece_program, "ECE", "B")
    cse_a = cohort(cse_program, "CSE", "A")

    def student(program, selected_cohort, admission, first_name):
        return _post("/api/college/students", owner_headers, {
            "first_name": first_name, "last_name": "Student",
            "email": f"{admission.lower()}@example.edu", "phone": "9876543210",
            "date_of_birth": "2005-01-10", "gender": "female",
            "guardian": {"name": "Private Guardian", "phone": "9000000000"},
            "home_location_id": location_id, "admission_number": admission,
            "program_id": program["id"], "cohort_id": selected_cohort["id"],
            "current_semester": 7, "admitted_on": "2023-07-01",
        })

    student_a = student(ece_program, ece_a, "ECE-A-001", "Asha")
    student_b = student(ece_program, ece_b, "ECE-B-001", "Bina")
    student_c = student(cse_program, cse_a, "CSE-A-001", "Charan")

    hod_email = f"hod-{uuid4().hex[:10]}@example.edu"
    with SessionLocal() as db:
        hod_role = db.execute(select(Role).where(
            Role.organization_id == organization_id, Role.slug == "hod",
        )).scalar_one()
        # A legacy/custom role may still carry generic sales grants. College
        # Finance must remain an explicit policy safeguard regardless.
        for code in ("sales.view", "sales.manage", "payments.record"):
            permission = db.execute(select(Permission).where(Permission.code == code)).scalar_one()
            if not db.execute(select(RolePermission).where(
                RolePermission.role_id == hod_role.id,
                RolePermission.permission_id == permission.id,
            )).scalar_one_or_none():
                db.add(RolePermission(role_id=hod_role.id, permission_id=permission.id))
        db.commit()
        hod_role_id = hod_role.id

    created = client.post("/api/users", headers=owner_headers, json={
        "email": hod_email, "first_name": "Ece", "last_name": "Hod",
        "password": "Testing@123", "role_ids": [hod_role_id], "location_ids": [],
    })
    assert created.status_code == 201, created.text
    hod_user_id = created.json()["id"]

    current_policy = client.get(f"/api/access/users/{hod_user_id}/policy", headers=owner_headers)
    assert current_policy.status_code == 200, current_policy.text
    policy_body = {
        "role_ids": [hod_role_id],
        "maximum_reach": [{"scope_type": "department", "scope_value": ece["id"]}],
        "domain_levels": {
            "students": "view", "academics": "view", "attendance": "work",
            "assessments": "work", "readiness": "view", "placements": "view",
            "reports": "view",
        },
        "domain_scope_limits": {
            domain: [{"scope_type": "cohort", "scope_value": ece_a["id"]}]
            for domain in ("students", "readiness", "placements")
        },
        "sensitive_capabilities": [], "ai_enabled": True,
        "review_note": "ECE HOD with Section A student responsibility",
        "version": current_policy.json()["version"],
    }
    saved = client.put(
        f"/api/access/users/{hod_user_id}/policy", headers=owner_headers, json=policy_body,
    )
    assert saved.status_code == 200, saved.text

    with SessionLocal() as db:
        hod = db.get(User, hod_user_id)
        hod.email_verified = True
        db.commit()

    login = client.post("/api/auth/login", json={
        "email": hod_email, "password": "Testing@123",
        "org_slug": context["organization"]["slug"],
    })
    assert login.status_code == 200, login.text
    hod_headers = {"Authorization": f"Bearer {login.cookies.get(settings.ACCESS_COOKIE_NAME)}"}

    hierarchy = client.get("/api/college/academic-hierarchy", headers=hod_headers)
    assert hierarchy.status_code == 200, hierarchy.text
    visible_departments = {
        department["id"]
        for batch in hierarchy.json()["items"]
        for department in batch["departments"]
    }
    assert visible_departments == {ece["id"]}

    student_hierarchy = client.get("/api/college/students/hierarchy", headers=hod_headers)
    assert student_hierarchy.status_code == 200, student_hierarchy.text
    visible_sections = {
        section["id"]
        for batch in student_hierarchy.json()["items"]
        for department in batch["departments"]
        for program in department["programs"]
        for section in program["sections"]
    }
    assert visible_sections == {ece_a["id"]}

    student_summary = client.get("/api/college/students/summary", headers=hod_headers, params={
        "graduation_year": 2027,
    })
    assert student_summary.status_code == 200, student_summary.text
    assert student_summary.json()["total_students"] == 1
    assert student_summary.json()["capabilities"]["readiness"] is True
    assert student_summary.json()["capabilities"]["placements"] is True

    academic_summary = client.get("/api/college/academics/summary", headers=hod_headers)
    assert academic_summary.status_code == 200, academic_summary.text
    assert academic_summary.json()["metrics"]["students_in_scope"] == 1
    assert academic_summary.json()["structure"]["departments"] == 1
    assert academic_summary.json()["structure"]["cohorts"] == 2

    # The HOD's academic reach includes ECE B, while the Students domain is
    # narrowed to ECE A. Academic metrics remain available without leaking a
    # misleading student count from the narrower domain.
    academic_b = client.get("/api/college/academics/summary", headers=hod_headers, params={
        "cohort_id": ece_b["id"],
    })
    assert academic_b.status_code == 200, academic_b.text
    assert academic_b.json()["metrics"]["students_in_scope"] is None
    assert academic_b.json()["capabilities"]["students"] is False
    assert academic_b.json()["structure"]["cohorts"] == 1

    outside_academics = client.get("/api/college/academics/summary", headers=hod_headers, params={
        "cohort_id": cse_a["id"],
    })
    assert outside_academics.status_code == 404

    student_page = client.get("/api/college/students/page", headers=hod_headers, params={
        "graduation_year": 2027,
        "limit": 25,
    })
    assert student_page.status_code == 200, student_page.text
    assert [row["id"] for row in student_page.json()["items"]] == [student_a["id"]]
    assert student_page.json()["next_cursor"] is None
    assert student_page.json()["capabilities"]["contact"] is False

    outside_summary = client.get("/api/college/students/summary", headers=hod_headers, params={
        "cohort_id": ece_b["id"],
    })
    assert outside_summary.status_code == 403

    cohorts = client.get("/api/college/cohorts/page", headers=hod_headers)
    assert cohorts.status_code == 200, cohorts.text
    assert {row["id"] for row in cohorts.json()["items"]} == {ece_a["id"], ece_b["id"]}

    directory = client.get("/api/clients", headers=hod_headers)
    assert directory.status_code == 200, directory.text
    assert [row["id"] for row in directory.json()["items"]] == [student_a["client_id"]]
    visible = directory.json()["items"][0]
    assert visible["email"] is None
    assert visible["phone"] is None
    assert visible["date_of_birth"] is None
    assert visible["gender"] is None

    for hidden_student in (student_b, student_c):
        response = client.get(f"/api/clients/{hidden_student['client_id']}", headers=hod_headers)
        assert response.status_code == 404

    workspace = client.get(f"/api/clients/{student_a['client_id']}/workspace", headers=hod_headers)
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()["client"]["date_of_birth"] is None
    assert workspace.json()["signals"] == []
    assert workspace.json()["actions"]["view_billing"] is False

    dashboard = client.get("/api/college/placement-dashboard", headers=hod_headers)
    assert dashboard.status_code == 200, dashboard.text
    assert {row["id"] for row in dashboard.json()["filters"]["cohorts"]} == {ece_a["id"]}

    finance = client.get("/api/sales/workspace", headers=hod_headers)
    assert finance.status_code == 403

    latest = client.get(f"/api/access/users/{hod_user_id}/policy", headers=owner_headers).json()
    revoked = client.put(
        f"/api/access/users/{hod_user_id}/policy", headers=owner_headers,
        json={**policy_body, "domain_levels": {}, "ai_enabled": False, "version": latest["version"]},
    )
    assert revoked.status_code == 200, revoked.text
    stale = client.get("/api/clients", headers=hod_headers)
    assert stale.status_code == 401
    assert stale.json()["error"]["code"] == "access_changed"


def test_college_structure_erp_linking_requires_review_and_preserves_manual_overrides(college_account):
    headers, context, organization_id = college_account
    department = _post("/api/college/departments", headers, {
        "name": "Information Technology",
        "code": "IT",
        "location_id": context["locations"][0]["id"],
    })
    connector = _post("/api/college/integrations", headers, {
        "name": "Academic ERP",
        "base_url": "https://erp.example.edu/api",
        "auth_mode": "bearer",
        "mapping": {},
        "pagination": {},
        "sync_interval_hours": 6,
    })
    source_row = {
        "external_id": "erp-department-it",
        "name": "Department of Information Technology",
        "code": "IT",
        "source_updated_at": "2026-08-13T08:00:00Z",
    }

    with SessionLocal() as db:
        owner = db.execute(select(User).where(User.organization_id == organization_id)).scalar_one()
        run = stage_rows(
            db, organization_id=organization_id, user_id=owner.id,
            source_type="erp", resource_type="departments", rows=[source_row], mapping={},
            connector_id=connector["id"], idempotency_key="erp-it-collision-1",
        )
        commit_run(db, run)
        db.commit()
        assert run.committed_count == 0
        assert "review and link" in run.validation_errors[0]["errors"][0]

    link = _post("/api/college/integrations/structure-links", headers, {
        "connector_id": connector["id"],
        "resource_type": "departments",
        "external_id": source_row["external_id"],
        "local_resource_id": department["id"],
        "manual_override_fields": [],
    })
    with SessionLocal() as db:
        owner = db.execute(select(User).where(User.organization_id == organization_id)).scalar_one()
        run = stage_rows(
            db, organization_id=organization_id, user_id=owner.id,
            source_type="erp", resource_type="departments", rows=[source_row], mapping={},
            connector_id=connector["id"], idempotency_key="erp-it-linked-2",
        )
        commit_run(db, run)
        db.commit()
        assert run.committed_count == 1
        updated = db.get(CollegeDepartment, department["id"])
        assert updated.name == source_row["name"]

    override = client.patch(
        f"/api/college/integrations/structure-links/{link['id']}", headers=headers,
        json={"manual_override_fields": ["name"]},
    )
    assert override.status_code == 200, override.text
    with SessionLocal() as db:
        owner = db.execute(select(User).where(User.organization_id == organization_id)).scalar_one()
        run = stage_rows(
            db, organization_id=organization_id, user_id=owner.id,
            source_type="erp", resource_type="departments",
            rows=[{
                **source_row,
                "name": "ERP must not replace this name",
                "source_updated_at": "2026-08-13T09:00:00Z",
            }], mapping={},
            connector_id=connector["id"], idempotency_key="erp-it-override-3",
        )
        commit_run(db, run)
        db.commit()
        preserved = db.get(CollegeDepartment, department["id"])
        assert preserved.name == source_row["name"]
        assert preserved.is_active is True

    with SessionLocal() as db:
        owner = db.execute(select(User).where(User.organization_id == organization_id)).scalar_one()
        stale = stage_rows(
            db, organization_id=organization_id, user_id=owner.id,
            source_type="erp", resource_type="departments",
            rows=[{
                **source_row,
                "name": "Stale ERP department name",
                "source_updated_at": "2026-08-13T08:30:00Z",
            }], mapping={},
            connector_id=connector["id"], idempotency_key="erp-it-stale-4",
        )
        commit_run(db, stale)
        db.commit()
        assert stale.committed_count == 0
        assert "older than the latest" in stale.validation_errors[0]["errors"][0]
        preserved = db.get(CollegeDepartment, department["id"])
        assert preserved.name == source_row["name"]


def test_college_workspace_connects_academics_students_attendance_results_and_fees(college_account):
    headers, context, organization_id = college_account
    location_id = context["locations"][0]["id"]

    empty = client.get("/api/college/workspace", headers=headers, params={"location_id": location_id})
    assert empty.status_code == 200, empty.text
    assert empty.json()["summary"]["active_students"] == 0

    department = _post("/api/college/departments", headers, {
        "name": "Computer Science",
        "code": "CS",
        "location_id": location_id,
    })
    program = _post("/api/college/programs", headers, {
        "department_id": department["id"],
        "name": "B.Sc. Computer Science",
        "code": "BSC-CS",
        "degree_type": "undergraduate",
        "duration_semesters": 6,
    })
    term = _post("/api/college/terms", headers, {
        "name": "Semester 1",
        "academic_year": "2026-27",
        "term_number": 1,
        "starts_on": "2026-07-01",
        "ends_on": "2026-12-15",
        "status": "active",
        "is_current": True,
    })
    cohort = _post("/api/college/cohorts", headers, {
        "program_id": program["id"],
        "name": "B.Sc. CS 2026 / A",
        "code": "BSC-CS-2026-A",
        "admission_year": 2026,
        "current_semester": 1,
        "section": "A",
    })
    assert cohort["graduation_year"] == 2029
    course = _post("/api/college/courses", headers, {
        "department_id": department["id"],
        "name": "Programming Fundamentals",
        "code": "CS101",
        "credits": 4,
        "course_type": "core",
    })
    offering = _post("/api/college/offerings", headers, {
        "term_id": term["id"],
        "course_id": course["id"],
        "cohort_id": cohort["id"],
        "room": "Lab 1",
        "weekly_schedule": [{
            "weekday": 0,
            "starts_at": "09:00:00",
            "ends_at": "10:00:00",
            "room": "Lab 1",
        }],
    })
    student = _post("/api/college/students", headers, {
        "first_name": "Asha",
        "last_name": "Raman",
        "email": "asha.college@example.com",
        "phone": "9884000001",
        "home_location_id": location_id,
        "admission_number": "ADM-2026-001",
        "roll_number": "CS-001",
        "program_id": program["id"],
        "cohort_id": cohort["id"],
        "current_semester": 1,
        "admitted_on": "2026-07-10",
        "guardian": {"name": "Raman", "phone": "9884000099"},
    })

    # College tenants must use admission so no ownerless generic Client can be created.
    generic = client.post("/api/clients", headers=headers, json={
        "first_name": "Not a student",
        "phone": "9884000002",
        "home_location_id": location_id,
    })
    assert generic.status_code == 409
    assert "student admission" in generic.json()["detail"].lower()

    search = client.get("/api/search", headers=headers, params={"q": "Not a student"})
    assert search.status_code == 200, search.text
    assert search.json()["clients"] == []
    student_search = client.get("/api/search", headers=headers, params={"q": "ADM-2026-001"})
    assert student_search.status_code == 200, student_search.text
    assert student["client_id"] in {row["id"] for row in student_search.json()["clients"]}

    directory = client.get("/api/clients/directory", headers=headers, params={
        "location_id": location_id,
        "segment": "active",
    })
    assert directory.status_code == 200, directory.text
    assert directory.json()["summary"]["total"] == 1
    assert directory.json()["summary"]["active"] == 1
    assert [row["admission_number"] for row in directory.json()["items"]] == ["ADM-2026-001"]

    # Enrollment status, not the generic Client status, controls active/inactive scopes.
    with SessionLocal() as db:
        profile = db.get(CollegeStudentProfile, student["id"])
        profile.status = "inactive"
        db.commit()
    active = client.get("/api/clients/directory", headers=headers, params={"segment": "active"}).json()
    inactive = client.get("/api/clients/directory", headers=headers, params={"segment": "inactive"}).json()
    assert active["summary"]["active"] == 0
    assert active["items"] == []
    assert len(inactive["items"]) == 1
    with SessionLocal() as db:
        profile = db.get(CollegeStudentProfile, student["id"])
        profile.status = "active"
        db.commit()

    attendance = _post("/api/college/attendance", headers, {
        "offering_id": offering["id"],
        "held_on": "2026-08-06",
        "starts_at": "09:00:00",
        "ends_at": "10:00:00",
        "topic": "Variables and data types",
        "records": [{"student_profile_id": student["id"], "status": "present"}],
    })
    records = client.get(f"/api/college/attendance/{attendance['id']}/records", headers=headers)
    assert records.status_code == 200, records.text
    assert records.json()[0]["student_name"] == "Asha Raman"

    assessment = _post("/api/college/assessments", headers, {
        "offering_id": offering["id"],
        "title": "Internal assessment 1",
        "assessment_type": "internal",
        "max_marks": 50,
        "weightage_bps": 2000,
        "due_on": "2026-08-20",
        "status": "draft",
    })
    scores = client.put(f"/api/college/assessments/{assessment['id']}/scores", headers=headers, json={
        "publish": True,
        "scores": [{"student_profile_id": student["id"], "marks_awarded": 43, "grade": "A"}],
    })
    assert scores.status_code == 200, scores.text
    assert scores.json()["status"] == "published"

    references = client.get("/api/college/references", headers=headers)
    assert references.status_code == 200, references.text
    assert references.json()["programs"][0]["id"] == program["id"]

    cohorts_page = client.get("/api/college/cohorts/page", headers=headers, params={"limit": 1})
    assert cohorts_page.status_code == 200, cohorts_page.text
    assert set(cohorts_page.json()) >= {"items", "next_cursor", "has_more"}
    assert cohorts_page.json()["items"][0]["student_count"] == 1

    sessions_page = client.get("/api/college/attendance/sessions/page", headers=headers, params={"limit": 1})
    assert sessions_page.status_code == 200, sessions_page.text
    assert sessions_page.json()["items"][0]["id"] == attendance["id"]
    scoped_sessions = client.get("/api/college/attendance/sessions/page", headers=headers, params={
        "academic_year_id": "2026-27",
        "term_id": term["id"],
        "department_id": department["id"],
        "program_id": program["id"],
        "cohort_id": cohort["id"],
    })
    assert scoped_sessions.status_code == 200, scoped_sessions.text
    assert [row["id"] for row in scoped_sessions.json()["items"]] == [attendance["id"]]
    mismatched_period = client.get("/api/college/attendance/sessions/page", headers=headers, params={
        "academic_year_id": "2027-28",
        "term_id": term["id"],
    })
    assert mismatched_period.status_code == 422
    attendance_register = client.get(f"/api/college/attendance/{attendance['id']}/register", headers=headers, params={"limit": 1})
    assert attendance_register.status_code == 200, attendance_register.text
    assert attendance_register.json()["items"][0]["student_name"] == "Asha Raman"
    assert attendance_register.json()["items"][0]["status"] == "present"

    assessments_page = client.get("/api/college/assessments/page", headers=headers, params={"limit": 1})
    assert assessments_page.status_code == 200, assessments_page.text
    assert assessments_page.json()["items"][0]["id"] == assessment["id"]
    scoped_assessments = client.get("/api/college/assessments/page", headers=headers, params={
        "academic_year_id": "2026-27",
        "term_id": term["id"],
        "department_id": department["id"],
        "program_id": program["id"],
        "cohort_id": cohort["id"],
    })
    assert scoped_assessments.status_code == 200, scoped_assessments.text
    assert [row["id"] for row in scoped_assessments.json()["items"]] == [assessment["id"]]
    assessment_register = client.get(f"/api/college/assessments/{assessment['id']}/register", headers=headers, params={"limit": 1})
    assert assessment_register.status_code == 200, assessment_register.text
    assert assessment_register.json()["items"][0]["marks_awarded"] == 43.0

    intelligence_page = client.get("/api/college/student-intelligence", headers=headers, params={"limit": 1})
    assert intelligence_page.status_code == 200, intelligence_page.text
    assert intelligence_page.json()["items"][0]["admission_number"] == "ADM-2026-001"
    assert intelligence_page.json()["has_more"] is False

    malformed = client.get("/api/college/cohorts/page", headers=headers, params={"cursor": "invalid"})
    assert malformed.status_code == 422

    fee_plan = _post("/api/college/fee-plans", headers, {
        "name": "Semester 1 tuition",
        "program_id": program["id"],
        "cohort_id": cohort["id"],
        "term_id": term["id"],
        "amount_paise": 500000,
        "due_on": "2026-08-31",
        "line_items": [
            {"name": "Tuition fee", "amount_paise": 400000},
            {"name": "Academic services", "amount_paise": 100000},
        ],
    })
    fee_payload = {
        "student_profile_id": student["id"],
        "fee_plan_id": fee_plan["id"],
        "concession_paise": 50000,
        "idempotency_key": f"college-fee-{uuid4().hex}",
    }
    fee = _post("/api/college/student-fees", headers, fee_payload)
    repeated = _post("/api/college/student-fees", headers, fee_payload)
    assert repeated["id"] == fee["id"]
    assert repeated["invoice"]["id"] == fee["invoice"]["id"]
    duplicate = client.post("/api/college/student-fees", headers=headers, json={
        **fee_payload,
        "idempotency_key": f"college-fee-{uuid4().hex}",
    })
    assert duplicate.status_code == 409

    workspace = client.get("/api/college/workspace", headers=headers, params={"location_id": location_id}).json()
    assert workspace["summary"]["active_students"] == 1
    assert workspace["summary"]["attendance_percent"] == 100.0
    assert workspace["summary"]["fees_outstanding_paise"] == 450000
    assert workspace["student_fees"][0]["student_name"] == "Asha Raman"
    assert workspace["student_fees"][0]["invoice_number"]

    invoice = client.get(f"/api/sales/{fee['invoice']['id']}", headers=headers)
    assert invoice.status_code == 200, invoice.text
    assert invoice.json()["client"]["display_name"] == "Asha Raman"
    assert [row["item_name"] for row in invoice.json()["lines"]] == ["Tuition fee", "Academic services"]

    dashboard = client.get("/api/dashboard/workspace", headers=headers, params={
        "location_id": location_id,
        "range": 30,
    })
    assert dashboard.status_code == 409, dashboard.text
    assert "placement intelligence dashboard" in dashboard.json()["detail"]

    profile = client.get(f"/api/clients/{student['client_id']}/workspace", headers=headers)
    assert profile.status_code == 200, profile.text
    assert profile.json()["industry"] == "college"
    assert profile.json()["industry_data"]["profile"]["admission_number"] == "ADM-2026-001"
    assert profile.json()["industry_data"]["attendance_summary"]["percentage"] == 100.0

    intelligence = client.get(f"/api/college/students/{student['id']}/intelligence", headers=headers)
    assert intelligence.status_code == 200, intelligence.text
    assert intelligence.json()["fee_clearance"]["status"] == "pending"
    clearance_page = client.get("/api/college/internship-clearance/page", headers=headers, params={"clearance": "pending"})
    assert clearance_page.status_code == 200, clearance_page.text
    assert clearance_page.json()["items"][0]["student_name"] == "Asha Raman"
    assert "outstanding_paise" not in clearance_page.json()["items"][0]

    company = _post("/api/college/companies", headers, {"name": "Internship Partner"})
    internship = _post("/api/college/opportunities", headers, {
        "company_id": company["id"],
        "title": "Software Engineering Intern",
        "opportunity_type": "internship",
        "status": "active",
    })
    assert internship["eligibility_rules"]["require_fee_clearance"] is True
    blocked = client.post("/api/college/applications", headers=headers, json={
        "opportunity_id": internship["id"],
        "student_profile_id": student["id"],
    })
    assert blocked.status_code == 409
    assert "fee clearance" in blocked.json()["detail"].lower()

    payment = client.post(f"/api/sales/{fee['invoice']['id']}/payments", headers=headers, json={
        "amount_paise": 450000,
        "method": "upi",
        "idempotency_key": f"college-fee-payment-{uuid4().hex}",
    })
    assert payment.status_code == 201, payment.text
    cleared = client.get(f"/api/college/students/{student['id']}/intelligence", headers=headers)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["fee_clearance"]["status"] == "cleared"
    application = _post("/api/college/applications", headers, {
        "opportunity_id": internship["id"],
        "student_profile_id": student["id"],
    })
    fee_check = next(row for row in application["eligibility_evidence"]["checks"] if row["rule"] == "fee_clearance")
    assert fee_check["passes"] is True

    with SessionLocal() as db:
        assert db.get(Organization, organization_id) is not None

        # Simulate an organization created before College role templates and
        # permissions existed, then verify the non-destructive startup backfill.
        faculty_role = db.execute(select(Role).where(
            Role.organization_id == organization_id,
            Role.slug == "faculty",
        )).scalar_one()
        owner_role = db.execute(select(Role).where(
            Role.organization_id == organization_id,
            Role.slug == "owner",
        )).scalar_one()
        academic_permission = db.execute(select(Permission).where(
            Permission.code == "college.academics.manage",
        )).scalar_one()
        db.delete(faculty_role)
        db.execute(delete(RolePermission).where(
            RolePermission.role_id == owner_role.id,
            RolePermission.permission_id == academic_permission.id,
        ))
        db.flush()

        permissions = ensure_permissions(db)
        ensure_missing_business_roles(db, permissions)
        sync_granular_role_permissions(db, permissions)
        db.flush()

        assert db.execute(select(Role).where(
            Role.organization_id == organization_id,
            Role.slug == "faculty",
        )).scalar_one_or_none() is not None
        assert db.execute(select(RolePermission).where(
            RolePermission.role_id == owner_role.id,
            RolePermission.permission_id == academic_permission.id,
        )).scalar_one_or_none() is not None
        db.rollback()


def test_college_summary_language_is_selected_per_turn():
    result = {"industry": "college", "active_students": 12, "employees": 4}
    assert _summary_text(result, "en") == "You have 12 active students and 4 faculty and staff."
    assert "irukaanga" in _summary_text(result, "tanglish")
    tamil = _summary_text(result, "ta")
    assert "மாணவர்களும்" in tamil
    assert "There are" not in tamil


def test_college_opportunity_scope_and_batch_eligibility_are_isolated():
    access = CollegeAccess(
        unrestricted=False,
        student_ids=frozenset({"student-a"}),
        department_ids=frozenset({"department-a"}),
        program_ids=frozenset({"program-a"}),
        cohort_ids=frozenset({"cohort-a"}),
    )
    assert access.allows_opportunity({}) is True
    assert access.allows_opportunity({"department_ids": ["department-a"]}) is True
    assert access.allows_opportunity({"program_ids": ["program-a"]}) is True
    assert access.allows_opportunity({"cohort_ids": ["cohort-a"]}) is True
    assert access.allows_opportunity({"department_ids": ["department-b"]}) is False
    assert access.allows_opportunity({"program_ids": ["program-b"]}) is False
    assert access.allows_opportunity({"batch_ids": ["cohort-b"]}) is False

    evidence = {
        "program_id": "program-a",
        "department_id": "department-a",
        "cohort_id": "cohort-a",
        "skills": [],
    }
    assert evaluate_eligibility(evidence, {"cohort_ids": ["cohort-a"]})["status"] == "eligible"
    assert evaluate_eligibility(evidence, {"cohort_ids": ["cohort-b"]})["status"] == "ineligible"
    assert evaluate_eligibility({**evidence, "cohort_id": None}, {"cohort_ids": ["cohort-a"]})["status"] == "needs_review"


def test_college_fee_clearance_is_a_tri_state_eligibility_rule():
    rules = {"require_fee_clearance": True}
    assert evaluate_eligibility(
        {"skills": [], "fee_clearance": {"status": "cleared"}},
        rules,
    )["status"] == "eligible"
    assert evaluate_eligibility(
        {"skills": [], "fee_clearance": {"status": "pending"}},
        rules,
    )["status"] == "ineligible"
    assert evaluate_eligibility(
        {"skills": [], "fee_clearance": {"status": "not_assessed"}},
        rules,
    )["status"] == "needs_review"


def test_college_erp_urls_reject_private_hosts_and_cross_origin_pagination():
    public_dns = [(2, 1, 6, "", ("93.184.216.34", 443))]
    private_dns = [(2, 1, 6, "", ("127.0.0.1", 443))]
    with patch("app.services.college_jobs.socket.getaddrinfo", return_value=public_dns):
        base = _public_host("https://erp.example.com/api")
        origin = _url_origin(base)
        assert _public_host("https://erp.example.com/api/students", expected_origin=origin) == "https://erp.example.com/api/students"
        with pytest.raises(RuntimeError, match="configured host"):
            _public_host("https://attacker.example.net/collect", expected_origin=origin)
    with patch("app.services.college_jobs.socket.getaddrinfo", return_value=private_dns):
        with pytest.raises(RuntimeError, match="private or reserved"):
            _public_host("https://erp.example.com/api")


def test_college_placement_intelligence_is_evidence_backed_and_audited(college_account):
    headers, context, organization_id = college_account
    location_id = context["locations"][0]["id"]
    department = _post("/api/college/departments", headers, {
        "name": "Computer Science", "code": "CSE", "location_id": location_id,
    })
    program = _post("/api/college/programs", headers, {
        "department_id": department["id"], "name": "B.E. Computer Science",
        "code": "BE-CSE", "degree_type": "undergraduate", "duration_semesters": 8,
    })
    cohort = _post("/api/college/cohorts", headers, {
        "program_id": program["id"], "name": "CSE 2026 / A", "code": "CSE-2026-A",
        "admission_year": 2023, "current_semester": 7, "section": "A",
    })
    assert cohort["graduation_year"] == 2027

    def admit(number, first_name):
        return _post("/api/college/students", headers, {
            "first_name": first_name, "last_name": "Student",
            "email": f"{first_name.lower()}-{number.lower()}@example.com",
            "home_location_id": location_id, "admission_number": number,
            "roll_number": number.replace("ADM", "ROLL"), "program_id": program["id"],
            "cohort_id": cohort["id"], "current_semester": 7,
            "admitted_on": "2023-07-10",
        })

    ready_student = admit("ADM-PLC-001", "Asha")
    partial_student = admit("ADM-PLC-002", "Bala")

    career = client.put(f"/api/college/students/{ready_student['id']}/career", headers=headers, json={
        "participation_status": "participating", "graduation_year": 2027,
        "preferred_roles": ["Software Engineer"], "preferred_locations": ["Chennai"],
        "resume_status": "approved", "placement_status": "seeking",
    })
    assert career.status_code == 200, career.text
    for student_id, semester, cgpa in (
        (ready_student["id"], 7, 8.6),
        (partial_student["id"], 7, 8.2),
    ):
        response = client.post(f"/api/college/students/{student_id}/term-results", headers=headers, json={
            "semester": semester, "sgpa": cgpa, "cgpa": cgpa,
            "credits_earned": 132, "total_backlogs": 0, "active_backlogs": 0,
            "published_on": "2026-07-15",
        })
        assert response.status_code == 201, response.text

    hierarchy = client.get("/api/college/academic-hierarchy", headers=headers)
    assert hierarchy.status_code == 200, hierarchy.text
    batch = next(row for row in hierarchy.json()["items"] if row["graduation_year"] == 2027)
    hierarchy_department = next(row for row in batch["departments"] if row["id"] == department["id"])
    assert hierarchy_department["student_count"] == 2
    assert hierarchy_department["section_count"] == 1
    assert hierarchy_department["programs"][0]["sections"][0]["section"] == "A"

    cohort_page = client.get("/api/college/cohorts/page", headers=headers, params={
        "graduation_year": 2027,
        "department_id": department["id"],
        "cohort_id": cohort["id"],
    })
    assert cohort_page.status_code == 200, cohort_page.text
    assert len(cohort_page.json()["items"]) == 1
    assert cohort_page.json()["items"][0]["department_code"] == "CSE"
    assert cohort_page.json()["items"][0]["section"] == "A"

    academic_order = client.get("/api/college/student-intelligence", headers=headers, params={
        "graduation_year": 2027,
        "department_id": department["id"],
        "cohort_id": cohort["id"],
        "placement_status": "unplaced",
        "sort": "academics_desc",
    })
    assert academic_order.status_code == 200, academic_order.text
    assert [row["name"] for row in academic_order.json()["items"]] == ["Asha Student", "Bala Student"]
    assert all(row["graduation_year"] == 2027 and row["section"] == "A" for row in academic_order.json()["items"])

    with SessionLocal() as db:
        owner = db.execute(select(User).where(User.organization_id == organization_id)).scalar_one()
        ai_result = tool_college_students(
            db,
            owner,
            department="CSE",
            section="A",
            graduation_years=[2027],
            placement_status="unplaced",
            sort="academics_desc",
        )
        assert [row["name"] for row in ai_result["items"]] == ["Asha Student", "Bala Student"]
        assert ai_result["resolved_scope"]["department"]["id"] == department["id"]
        assert ai_result["resolved_scope"]["graduation_years"] == [2027]

    attendance = client.post(f"/api/college/students/{ready_student['id']}/attendance-snapshots", headers=headers, json={
        "scope": "overall", "classes_held": 120, "classes_attended": 108,
        "as_of": "2026-08-01",
    })
    assert attendance.status_code == 201, attendance.text
    assessment = client.post(f"/api/college/students/{ready_student['id']}/placement-assessments", headers=headers, json={
        "assessment_type": "technical", "title": "Placement technical assessment",
        "score_percent": 84, "assessed_on": "2026-07-28", "provider": "Placement cell",
    })
    assert assessment.status_code == 201, assessment.text
    preparation = client.post(f"/api/college/students/{ready_student['id']}/preparation", headers=headers, json={
        "activity_type": "mock_interview", "title": "Technical mock interview",
        "status": "completed", "occurred_on": "2026-07-30", "outcome_score": 88,
    })
    assert preparation.status_code == 201, preparation.text
    intervention = client.post(f"/api/college/students/{ready_student['id']}/interventions", headers=headers, json={
        "reason_code": "mock_interview_follow_up", "title": "Review system design feedback",
        "note": "Schedule a follow-up mock interview", "priority": "high", "due_on": "2026-08-20",
    })
    assert intervention.status_code == 201, intervention.text
    for evidence_type, title in (("skill", "Python"), ("project", "Placement portal"), ("certification", "Cloud fundamentals")):
        response = client.post(f"/api/college/students/{ready_student['id']}/evidence", headers=headers, json={
            "evidence_type": evidence_type, "title": title, "is_verified": True,
        })
        assert response.status_code == 201, response.text
    account = client.put(f"/api/college/students/{ready_student['id']}/coding-account", headers=headers, json={
        "username": "asha-placement", "consent_status": "granted", "verification_status": "verified",
    })
    assert account.status_code == 200, account.text
    coding = client.post(f"/api/college/students/{ready_student['id']}/coding-snapshots", headers=headers, json={
        "captured_at": "2026-08-05T10:00:00Z", "easy_solved": 90,
        "medium_solved": 65, "hard_solved": 12, "contest_rating": 1660,
        "languages": ["Python", "C++"],
    })
    assert coding.status_code == 201, coding.text

    recompute = client.post("/api/college/readiness/recompute", headers=headers)
    assert recompute.status_code == 200, recompute.text
    assert recompute.json()["recomputed"] == 2

    ready_profile = client.get(f"/api/college/students/{ready_student['id']}/intelligence", headers=headers)
    assert ready_profile.status_code == 200, ready_profile.text
    ready_payload = ready_profile.json()
    assert ready_payload["readiness"]["coverage_percent"] == 100.0
    assert ready_payload["readiness"]["score"] > 0
    assert "gender" not in ready_payload["readiness"]["factors"]
    assert "category" not in ready_payload["readiness"]["factors"]
    assert ready_payload["interventions"][0]["title"] == "Review system design feedback"
    assert any(row["type"] == "intervention" for row in ready_payload["activity"])

    partial_profile = client.get(f"/api/college/students/{partial_student['id']}/intelligence", headers=headers).json()
    assert partial_profile["readiness"]["score"] == pytest.approx(82.0)
    assert partial_profile["readiness"]["coverage_percent"] == 25.0
    assert partial_profile["readiness"]["rankable"] is False
    assert set(partial_profile["readiness"]["missing_evidence"]) == {
        "coding", "assessment", "profile", "attendance", "training",
    }

    company = _post("/api/college/companies", headers, {
        "name": "Northstar Technologies", "industry": "Software",
    })
    protected = client.post("/api/college/opportunities", headers=headers, json={
        "company_id": company["id"], "title": "Protected shortlist",
        "eligibility_rules": {"gender": "female"},
    })
    assert protected.status_code == 422
    nested_protected = client.post("/api/college/opportunities", headers=headers, json={
        "company_id": company["id"], "title": "Nested protected shortlist",
        "eligibility_rules": {"profile": {"guardian_income": {"minimum": 1}}},
    })
    assert nested_protected.status_code == 422

    opportunity = _post("/api/college/opportunities", headers, {
        "company_id": company["id"], "title": "Graduate Software Engineer",
        "status": "active", "package_min_paise": 70000000,
        "eligibility_rules": {
            "department_ids": [department["id"]], "minimum_cgpa": 8,
            "maximum_active_backlogs": 0, "minimum_attendance": 75,
            "minimum_solved": 100, "required_skills": ["Python"],
        },
    })
    evaluated = client.post(f"/api/college/opportunities/{opportunity['id']}/evaluate", headers=headers)
    assert evaluated.status_code == 200, evaluated.text
    statuses = {row["student_id"]: row["status"] for row in evaluated.json()["items"]}
    assert statuses[ready_student["id"]] == "eligible"
    assert statuses[partial_student["id"]] == "needs_review"

    application = _post("/api/college/applications", headers, {
        "opportunity_id": opportunity["id"], "student_profile_id": ready_student["id"],
    })
    stages = client.get("/api/college/pipeline/stages", headers=headers).json()["items"]
    applied_stage = next(row for row in stages if row["slug"] == "applied")
    moved = client.patch(f"/api/college/applications/{application['id']}/stage", headers=headers, json={
        "stage_id": applied_stage["id"], "reason": "Student submitted the application", "version": 1,
    })
    assert moved.status_code == 200, moved.text
    overridden = client.patch(f"/api/college/applications/{application['id']}/eligibility-override", headers=headers, json={
        "status": "eligible", "reason": "Placement Head verified source records", "version": 2,
    })
    assert overridden.status_code == 200, overridden.text
    offer = client.post(f"/api/college/applications/{application['id']}/offers", headers=headers, json={
        "offered_role": "Graduate Software Engineer", "package_paise": 75000000,
        "offered_on": "2026-08-06", "status": "accepted",
    })
    assert offer.status_code == 201, offer.text
    application_list = client.get(
        "/api/college/applications",
        headers=headers,
        params={"opportunity_id": opportunity["id"]},
    )
    assert application_list.status_code == 200, application_list.text
    listed_application = application_list.json()["items"][0]
    assert listed_application["student"]["name"] == "Asha Student"
    assert listed_application["opportunity"]["title"] == "Graduate Software Engineer"
    assert listed_application["company"]["name"] == "Northstar Technologies"
    assert listed_application["stage"]["slug"] == "applied"

    dashboard = client.get("/api/college/placement-dashboard", headers=headers)
    assert dashboard.status_code == 200, dashboard.text
    dashboard_payload = dashboard.json()
    assert dashboard_payload["metrics"]["participating_students"] == 2
    assert dashboard_payload["metrics"]["offers"] == 1
    assert dashboard_payload["placement_funnel"]
    assert dashboard_payload["department_comparison"][0]["department"] == "Computer Science"
    assert dashboard_payload["brief"]
    assert "active_drive_deadlines" in dashboard_payload
    assert set(application_list.json()) >= {"items", "next_cursor", "has_more"}
    companies_page = client.get("/api/college/companies", headers=headers, params={"limit": 1})
    opportunities_page = client.get("/api/college/opportunities", headers=headers, params={"limit": 1})
    assert set(companies_page.json()) >= {"items", "next_cursor", "has_more"}
    assert set(opportunities_page.json()) >= {"items", "next_cursor", "has_more"}
    leaderboards = client.get("/api/college/leaderboards", headers=headers)
    assert leaderboards.status_code == 200, leaderboards.text
    assert leaderboards.json()["readiness"][0]["rank"] == 1

    import_key = f"skills-{uuid4().hex}"
    preview_body = {
        "resource_type": "skills", "idempotency_key": import_key,
        "rows": [{
            "external_id": "skill-001", "admission_number": "ADM-PLC-001",
            "title": "SQL", "proficiency": "advanced", "verified": True,
        }],
    }
    preview = client.post("/api/college/imports/preview", headers=headers, json=preview_body)
    assert preview.status_code == 201, preview.text
    committed = client.post(f"/api/college/imports/{preview.json()['id']}/commit", headers=headers)
    assert committed.status_code == 200, committed.text
    repeated_preview = client.post("/api/college/imports/preview", headers=headers, json=preview_body)
    assert repeated_preview.json()["id"] == preview.json()["id"]
    repeated_commit = client.post(f"/api/college/imports/{preview.json()['id']}/commit", headers=headers)
    assert repeated_commit.status_code == 200

    with SessionLocal() as db:
        events = list(db.execute(select(CollegeApplicationStageEvent).where(
            CollegeApplicationStageEvent.application_id == application["id"],
        )).scalars())
        assert len(events) == 2
        imported_skills = list(db.execute(select(CollegeCareerEvidence).where(
            CollegeCareerEvidence.organization_id == organization_id,
            CollegeCareerEvidence.student_profile_id == ready_student["id"],
            CollegeCareerEvidence.title == "SQL",
        )).scalars())
        assert len(imported_skills) == 1
