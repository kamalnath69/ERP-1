"""End-to-end coverage for the College industry workspace."""
from uuid import uuid4
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.ai.fast_queries import _summary_text
from app.core.config import settings
from app.core.database import SessionLocal
from app.db.seed import ensure_missing_business_roles, ensure_permissions, sync_granular_role_permissions
from app.models import (
    CollegeApplicationStageEvent, CollegeCareerEvidence, CollegeStudentProfile,
    Organization, Permission, Role, RolePermission, User,
)
from app.services.college_access import CollegeAccess
from app.services.college_placement import evaluate_eligibility
from app.services.college_jobs import _public_host, _url_origin
from server import app


client = TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def college_account():
    unique = uuid4().hex[:10]
    slug = f"test-college-{unique}"
    email = f"owner-{unique}@example.com"
    created_id = None
    response = client.post("/api/auth/register", json={
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
    assert response.status_code == 201, response.text
    with SessionLocal() as db:
        organization = db.execute(select(Organization).where(Organization.slug == slug)).scalar_one()
        owner = db.execute(select(User).where(User.organization_id == organization.id)).scalar_one()
        owner.email_verified = True
        created_id = organization.id
        db.commit()

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

    # A generic shared Client must not leak into a College student directory.
    generic = _post("/api/clients", headers, {
        "first_name": "Not a student",
        "phone": "9884000002",
        "home_location_id": location_id,
    })
    assert generic["id"] != student["client_id"]

    search = client.get("/api/search", headers=headers, params={"q": "Not a student"})
    assert search.status_code == 200, search.text
    assert generic["id"] not in {row["id"] for row in search.json()["clients"]}
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
    attendance_register = client.get(f"/api/college/attendance/{attendance['id']}/register", headers=headers, params={"limit": 1})
    assert attendance_register.status_code == 200, attendance_register.text
    assert attendance_register.json()["items"][0]["student_name"] == "Asha Raman"
    assert attendance_register.json()["items"][0]["status"] == "present"

    assessments_page = client.get("/api/college/assessments/page", headers=headers, params={"limit": 1})
    assert assessments_page.status_code == 200, assessments_page.text
    assert assessments_page.json()["items"][0]["id"] == assessment["id"]
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
    assert dashboard.status_code == 200, dashboard.text
    metrics = {row["id"]: row["value"] for row in dashboard.json()["metrics"]}
    assert metrics["active_students"] == 1
    assert metrics["outstanding"] == 450000
    assert "appointments_today" not in metrics
    assert "stock_risk" not in metrics

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
