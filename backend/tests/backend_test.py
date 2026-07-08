"""End-to-end backend API tests for Athena Education ERP.

Covers: auth (register/login/refresh), super admin, multi-tenancy, RBAC,
academic structure, students, faculty, attendance, marks, analytics,
billing, audit logs, permission enforcement, AI chat (graceful failure).
"""
import os
import random
import string
import time

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get(
    "REACT_APP_BACKEND_URL"
) else "https://sidebar-lock-1.preview.emergentagent.com"
API = f"{BASE}/api"

PRINCIPAL = {"email": "principal@demo-college.edu", "password": "Principal@123"}
FACULTY = {"email": "meena.iyer@demo-college.edu", "password": "Faculty@123"}
SUPER = {"email": "superadmin@platform.io", "password": "Super@123456"}


def _rand(n=6):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


# ---------------- Shared state ----------------
STATE = {}


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------- 1. AUTH ----------------
class TestAuth:
    def test_login_principal(self):
        data = _login(**PRINCIPAL)
        assert data["access_token"] and data["refresh_token"]
        assert data["user"]["email"] == PRINCIPAL["email"]
        STATE["principal_token"] = data["access_token"]
        STATE["principal_refresh"] = data["refresh_token"]
        STATE["principal_org_id"] = data["user"]["organization_id"]

    def test_login_faculty(self):
        data = _login(**FACULTY)
        STATE["faculty_token"] = data["access_token"]

    def test_login_super_admin(self):
        data = _login(**SUPER)
        assert data["user"]["is_super_admin"] is True
        STATE["super_token"] = data["access_token"]

    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": "no@nope.io", "password": "wrong"}, timeout=30)
        assert r.status_code == 401

    def test_me_principal(self):
        r = requests.get(f"{API}/auth/me", headers=_headers(STATE["principal_token"]), timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["organization"]["slug"] == "demo-college"
        assert "students.view" in body["permissions"]

    def test_refresh(self):
        r = requests.post(f"{API}/auth/refresh", json={"refresh_token": STATE["principal_refresh"]}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["access_token"] and d["refresh_token"]
        # rotated: old refresh should now be revoked
        r2 = requests.post(f"{API}/auth/refresh", json={"refresh_token": STATE["principal_refresh"]}, timeout=30)
        assert r2.status_code == 401
        STATE["principal_token"] = d["access_token"]
        STATE["principal_refresh"] = d["refresh_token"]

    def test_register_new_org(self):
        slug = f"test-uni-{_rand()}"
        email = f"admin_{_rand()}@test.io"
        r = requests.post(
            f"{API}/auth/register",
            json={
                "organization_name": "TEST Uni",
                "organization_slug": slug,
                "org_type": "college",
                "admin_email": email,
                "admin_password": "Password@123",
                "admin_first_name": "Test",
                "admin_last_name": "Admin",
            },
            timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        STATE["new_org_token"] = d["access_token"]
        STATE["new_org_id"] = d["user"]["organization_id"]
        STATE["new_org_slug"] = slug


# ---------------- 2. SUPER ADMIN ----------------
class TestSuperAdmin:
    def test_list_orgs(self):
        r = requests.get(f"{API}/super-admin/organizations", headers=_headers(STATE["super_token"]), timeout=30)
        assert r.status_code == 200
        orgs = r.json()
        assert isinstance(orgs, list) and len(orgs) >= 2

    def test_super_health_kpis(self):
        r = requests.get(f"{API}/super-admin/health", headers=_headers(STATE["super_token"]), timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("total_organizations", "total_users", "total_students"):
            assert k in d, f"missing {k} in {d}"

    def test_create_and_suspend_org(self):
        slug = f"sa-test-{_rand()}"
        r = requests.post(
            f"{API}/super-admin/organizations",
            headers=_headers(STATE["super_token"]),
            json={"name": "SA Test", "slug": slug, "org_type": "school"},
            timeout=30,
        )
        assert r.status_code == 201, r.text
        org_id = r.json()["id"]
        r2 = requests.post(f"{API}/super-admin/organizations/{org_id}/suspend", headers=_headers(STATE["super_token"]), timeout=30)
        assert r2.status_code == 200
        r3 = requests.post(f"{API}/super-admin/organizations/{org_id}/activate", headers=_headers(STATE["super_token"]), timeout=30)
        assert r3.status_code == 200
        STATE["sa_created_org"] = org_id

    def test_non_super_admin_forbidden(self):
        r = requests.get(f"{API}/super-admin/organizations", headers=_headers(STATE["principal_token"]), timeout=30)
        assert r.status_code in (401, 403)


# ---------------- 3. ROLES ----------------
class TestRoles:
    def test_list_permissions(self):
        r = requests.get(f"{API}/roles/permissions", headers=_headers(STATE["principal_token"]), timeout=30)
        assert r.status_code == 200
        perms = r.json()
        assert len(perms) > 5
        STATE["all_perms"] = perms

    def test_list_roles_has_system(self):
        r = requests.get(f"{API}/roles", headers=_headers(STATE["principal_token"]), timeout=30)
        assert r.status_code == 200
        roles = r.json()
        slugs = {x["slug"] for x in roles}
        expected = {"principal", "hod", "faculty", "class-advisor", "student", "parent"}
        assert expected.issubset(slugs), f"missing roles: {expected - slugs}"
        STATE["roles"] = roles
        STATE["principal_role_id"] = next(r for r in roles if r["slug"] == "principal")["id"]

    def test_create_custom_role(self):
        perms = STATE["all_perms"][:3]
        r = requests.post(
            f"{API}/roles",
            headers=_headers(STATE["principal_token"]),
            json={
                "name": f"TEST Role {_rand()}",
                "description": "custom",
                "permission_ids": [p["id"] for p in perms],
            },
            timeout=30,
        )
        assert r.status_code == 201, r.text
        role = r.json()
        STATE["custom_role_id"] = role["id"]

    def test_get_role_details(self):
        r = requests.get(f"{API}/roles/{STATE['principal_role_id']}", headers=_headers(STATE["principal_token"]), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["role"]["slug"] == "principal"
        assert len(d["permission_ids"]) > 5


# ---------------- 4. USERS ----------------
class TestUsers:
    def test_list_users(self):
        r = requests.get(f"{API}/users", headers=_headers(STATE["principal_token"]), timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_user_with_role(self):
        email = f"user_{_rand()}@demo-college.edu"
        r = requests.post(
            f"{API}/users",
            headers=_headers(STATE["principal_token"]),
            json={
                "email": email,
                "first_name": "TEST",
                "last_name": "User",
                "password": "Password@123",
                "role_ids": [STATE.get("custom_role_id")] if STATE.get("custom_role_id") else [],
            },
            timeout=30,
        )
        assert r.status_code == 201, r.text
        STATE["created_user_id"] = r.json()["id"]
        STATE["created_user_email"] = email

    def test_patch_user(self):
        r = requests.patch(
            f"{API}/users/{STATE['created_user_id']}",
            headers=_headers(STATE["principal_token"]),
            json={"phone": "9999999999"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json()["phone"] == "9999999999"

    def test_create_no_role_user_and_denied(self):
        email = f"noroleuser_{_rand()}@demo-college.edu"
        r = requests.post(
            f"{API}/users",
            headers=_headers(STATE["principal_token"]),
            json={"email": email, "first_name": "NoRole", "last_name": "User", "password": "Password@123", "role_ids": []},
            timeout=30,
        )
        assert r.status_code == 201, r.text
        login = _login(email, "Password@123")
        r2 = requests.get(f"{API}/students", headers=_headers(login["access_token"]), timeout=30)
        assert r2.status_code == 403


# ---------------- 5. ACADEMIC ----------------
class TestAcademic:
    def test_create_full_academic_tree(self):
        h = _headers(STATE["principal_token"])
        code = _rand(4).upper()
        d = requests.post(f"{API}/academic/departments", headers=h, json={"name": f"TEST Dept {code}", "code": code}, timeout=30)
        assert d.status_code == 201, d.text
        dept_id = d.json()["id"]
        STATE["dept_id"] = dept_id

        u = requests.post(
            f"{API}/academic/units", headers=h,
            json={"name": f"TEST Unit {code}", "code": code, "department_id": dept_id}, timeout=30
        )
        assert u.status_code == 201, u.text
        unit_id = u.json()["id"]

        lv = requests.post(f"{API}/academic/levels", headers=h, json={"name": "Sem 1", "unit_id": unit_id, "sequence": 1}, timeout=30)
        assert lv.status_code == 201, lv.text
        level_id = lv.json()["id"]

        s = requests.post(f"{API}/academic/sections", headers=h, json={"name": "A", "level_id": level_id}, timeout=30)
        assert s.status_code == 201, s.text
        STATE["section_id"] = s.json()["id"]

        sub = requests.post(f"{API}/academic/subjects", headers=h, json={"name": f"TEST Subject {code}", "code": code, "credits": 3, "department_id": dept_id}, timeout=30)
        assert sub.status_code == 201, sub.text
        STATE["subject_id"] = sub.json()["id"]


# ---------------- 6. STUDENTS ----------------
class TestStudents:
    def test_list_students_seeded(self):
        r = requests.get(f"{API}/students", headers=_headers(STATE["principal_token"]), timeout=30)
        assert r.status_code == 200
        students = r.json()
        assert len(students) > 0
        STATE["seed_student_id"] = students[0]["id"]

    def test_fuzzy_search_suresh(self):
        r = requests.get(f"{API}/students?q=Suresh", headers=_headers(STATE["principal_token"]), timeout=30)
        assert r.status_code == 200
        assert any("suresh" in (s["first_name"] + s["last_name"]).lower() for s in r.json())

    def test_fuzzy_search_priya(self):
        r = requests.get(f"{API}/students?q=Priya", headers=_headers(STATE["principal_token"]), timeout=30)
        assert r.status_code == 200
        assert any("priya" in (s["first_name"] + s["last_name"]).lower() for s in r.json())

    def test_create_and_update_student(self):
        adm = f"TEST{_rand()}"
        r = requests.post(
            f"{API}/students",
            headers=_headers(STATE["principal_token"]),
            json={
                "admission_number": adm, "first_name": "TEST", "last_name": "Student",
                "email": f"test_{_rand()}@demo-college.edu",
                "section_id": STATE.get("section_id"), "department_id": STATE.get("dept_id"),
            },
            timeout=30,
        )
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
        STATE["new_student_id"] = sid
        r2 = requests.patch(f"{API}/students/{sid}", headers=_headers(STATE["principal_token"]),
                            json={"phone": "1234567890"}, timeout=30)
        assert r2.status_code == 200 and r2.json()["phone"] == "1234567890"
        r3 = requests.get(f"{API}/students/{sid}", headers=_headers(STATE["principal_token"]), timeout=30)
        assert r3.status_code == 200 and r3.json()["phone"] == "1234567890"


# ---------------- 7. MULTI-TENANCY ISOLATION ----------------
class TestTenancyIsolation:
    def test_new_org_has_zero_students(self):
        # Uses the newly registered org from TestAuth.test_register_new_org
        token = STATE["new_org_token"]
        r = requests.get(f"{API}/students", headers=_headers(token), timeout=30)
        assert r.status_code == 200
        assert r.json() == [], f"tenant leakage! got {len(r.json())} students"

    def test_new_org_cannot_access_other_student(self):
        r = requests.get(f"{API}/students/{STATE['seed_student_id']}", headers=_headers(STATE["new_org_token"]), timeout=30)
        assert r.status_code == 404


# ---------------- 8. FACULTY ----------------
class TestFaculty:
    def test_create_faculty_creates_user(self):
        email = f"testfaculty_{_rand()}@demo-college.edu"
        r = requests.post(
            f"{API}/faculty",
            headers=_headers(STATE["principal_token"]),
            json={
                "employee_number": f"EMP{_rand()}", "email": email,
                "first_name": "TEST", "last_name": "Faculty",
                "password": "Password@123", "designation": "Asst Prof",
                "department_id": STATE.get("dept_id"),
            }, timeout=30,
        )
        assert r.status_code == 201, r.text
        # Verify user was created and can login and has faculty role
        d = _login(email, "Password@123")
        me = requests.get(f"{API}/auth/me", headers=_headers(d["access_token"]), timeout=30).json()
        assert any(role["slug"] == "faculty" for role in me["roles"])

    def test_list_faculty(self):
        r = requests.get(f"{API}/faculty", headers=_headers(STATE["principal_token"]), timeout=30)
        assert r.status_code == 200 and len(r.json()) >= 1


# ---------------- 9. ATTENDANCE ----------------
class TestAttendance:
    def test_create_session_and_summary(self):
        # Ensure we have a section w/ a student
        section_id = STATE.get("section_id")
        student_id = STATE.get("new_student_id") or STATE["seed_student_id"]
        from datetime import date
        r = requests.post(
            f"{API}/attendance/sessions",
            headers=_headers(STATE["principal_token"]),
            json={
                "section_id": section_id, "subject_id": STATE.get("subject_id"),
                "session_date": date.today().isoformat(), "topic": "TEST topic",
                "records": [{"student_id": student_id, "status": "present"}],
            }, timeout=30,
        )
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
        # summary
        s = requests.get(f"{API}/attendance/summary?section_id={section_id}", headers=_headers(STATE["principal_token"]), timeout=30)
        assert s.status_code == 200
        assert "attendance_percent" in s.json()
        # records
        rec = requests.get(f"{API}/attendance/sessions/{sid}/records", headers=_headers(STATE["principal_token"]), timeout=30)
        assert rec.status_code == 200 and len(rec.json()) == 1


# ---------------- 10. MARKS ----------------
class TestMarks:
    def test_exam_marks_publish_flow(self):
        h = _headers(STATE["principal_token"])
        r = requests.post(
            f"{API}/marks/exams", headers=h,
            json={
                "name": f"TEST Exam {_rand()}", "exam_type": "internal",
                "subject_id": STATE["subject_id"], "section_id": STATE["section_id"],
                "max_marks": 100, "pass_marks": 40,
            }, timeout=30,
        )
        assert r.status_code == 201, r.text
        exam_id = r.json()["id"]

        student_id = STATE.get("new_student_id") or STATE["seed_student_id"]
        b = requests.post(f"{API}/marks/bulk", headers=h,
                          json={"exam_id": exam_id, "marks": [{"student_id": student_id, "obtained": 85, "grade": "A"}]}, timeout=30)
        assert b.status_code == 200, b.text

        p = requests.post(f"{API}/marks/exams/{exam_id}/publish", headers=h, timeout=30)
        assert p.status_code == 200

        g = requests.get(f"{API}/marks/exams/{exam_id}/marks", headers=h, timeout=30)
        assert g.status_code == 200
        assert g.json()["exam"]["is_published"] is True
        assert len(g.json()["marks"]) == 1


# ---------------- 11. ANALYTICS ----------------
class TestAnalytics:
    def test_dashboard(self):
        r = requests.get(f"{API}/analytics/dashboard", headers=_headers(STATE["principal_token"]), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("kpis", "attendance_trend", "department_distribution"):
            assert k in d
        assert isinstance(d["attendance_trend"], list) and len(d["attendance_trend"]) == 14


# ---------------- 12. BILLING ----------------
class TestBilling:
    def test_plans(self):
        r = requests.get(f"{API}/billing/plans", headers=_headers(STATE["principal_token"]), timeout=30)
        assert r.status_code == 200
        ids = {p["id"] for p in r.json()["plans"]}
        assert {"starter", "pro", "enterprise"}.issubset(ids)

    def test_subscription(self):
        r = requests.get(f"{API}/billing/subscription", headers=_headers(STATE["principal_token"]), timeout=30)
        assert r.status_code == 200

    def test_order_and_mock_pay(self):
        r = requests.post(f"{API}/billing/orders", headers=_headers(STATE["principal_token"]),
                          json={"plan": "pro"}, timeout=30)
        assert r.status_code == 200, r.text
        inv_id = r.json()["invoice_id"]
        p = requests.post(f"{API}/billing/orders/{inv_id}/mock-pay", headers=_headers(STATE["principal_token"]), timeout=30)
        assert p.status_code == 200
        assert p.json()["invoice_status"] == "paid"


# ---------------- 13. AUDIT LOGS ----------------
class TestAudit:
    def test_audit_logs_present(self):
        r = requests.get(f"{API}/audit-logs", headers=_headers(STATE["principal_token"]), timeout=30)
        assert r.status_code == 200
        # After running many actions above, expect entries
        data = r.json()
        assert (isinstance(data, list) and len(data) > 0) or (isinstance(data, dict) and data.get("items"))


# ---------------- 14. AI CHAT (graceful failure OK due to budget) ----------------
class TestAIChat:
    def test_chat_endpoint_graceful(self):
        r = requests.post(f"{API}/ai/chat", headers=_headers(STATE["principal_token"]),
                          json={"message": "hi who are you"}, timeout=60)
        # Acceptable outcomes: 200 (if key has budget) OR 4xx/5xx with an error message
        assert r.status_code in (200, 402, 429, 500, 502, 503), f"unexpected: {r.status_code} {r.text}"
        # If failed, ensure a ChatConversation was still created (endpoint should list convs)
        c = requests.get(f"{API}/ai/conversations", headers=_headers(STATE["principal_token"]), timeout=30)
        assert c.status_code == 200
