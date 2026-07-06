"""Phase 2 backend tests - Parents, Assignments, Timetable, Calendar,
Fees, Library, Transport, Hostel, Placements, Admissions, Reports, Notifications."""
import os
import random
import string
import time

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://scholarly-ai-11.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

PRINCIPAL = {"email": "principal@demo-college.edu", "password": "Principal@123"}
FACULTY = {"email": "meena.iyer@demo-college.edu", "password": "Faculty@123"}


def _rand(n=6):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.text}"
    return r.json()


def _h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


STATE = {}


@pytest.fixture(scope="session", autouse=True)
def setup_tokens():
    p = _login(**PRINCIPAL)
    STATE["ptok"] = p["access_token"]
    STATE["porg"] = p["user"]["organization_id"]
    f = _login(**FACULTY)
    STATE["ftok"] = f["access_token"]
    # get me
    me = requests.get(f"{API}/auth/me", headers=_h(STATE["ptok"])).json()
    STATE["perms"] = me.get("permissions", [])
    # existing student/section/exam if any
    stu = requests.get(f"{API}/students", headers=_h(STATE["ptok"])).json()
    if isinstance(stu, list) and stu:
        STATE["student_id"] = stu[0]["id"]
        STATE["section_id"] = stu[0].get("section_id")
        STATE["department_id"] = stu[0].get("department_id")
    yield


# -------------------------- PARENTS
class TestParents:
    def test_create_parent(self):
        r = requests.post(f"{API}/parents", headers=_h(STATE["ptok"]), json={
            "first_name": "TEST_P", "last_name": _rand(), "email": f"TEST_{_rand()}@x.io", "phone": "555"
        })
        assert r.status_code == 201, r.text
        STATE["parent_id"] = r.json()["id"]

    def test_list_parents(self):
        r = requests.get(f"{API}/parents", headers=_h(STATE["ptok"]))
        assert r.status_code == 200
        assert any(p["id"] == STATE["parent_id"] for p in r.json())

    def test_link_parent(self):
        if not STATE.get("student_id"):
            pytest.skip("no student")
        r = requests.post(f"{API}/parents/link", headers=_h(STATE["ptok"]), json={
            "student_id": STATE["student_id"], "parent_id": STATE["parent_id"], "relationship": "father"
        })
        assert r.status_code == 200, r.text

    def test_of_student(self):
        if not STATE.get("student_id"):
            pytest.skip("no student")
        r = requests.get(f"{API}/parents/of-student/{STATE['student_id']}", headers=_h(STATE["ptok"]))
        assert r.status_code == 200
        assert any(p["id"] == STATE["parent_id"] for p in r.json())

    def test_rbac_faculty_forbidden(self):
        r = requests.post(f"{API}/parents", headers=_h(STATE["ftok"]), json={
            "first_name": "x", "last_name": "y"
        })
        assert r.status_code == 403

    def test_rbac_faculty_students_view(self):
        r = requests.get(f"{API}/students", headers=_h(STATE["ftok"]))
        assert r.status_code == 200


# -------------------------- ASSIGNMENTS
class TestAssignments:
    def test_prereq(self):
        # need faculty user + subject + section
        users = requests.get(f"{API}/users", headers=_h(STATE["ptok"])).json()
        fac = next((u for u in users if u["email"] == FACULTY["email"]), None)
        assert fac
        STATE["fac_user_id"] = fac["id"]
        subs = requests.get(f"{API}/academic/subjects", headers=_h(STATE["ptok"])).json()
        secs = requests.get(f"{API}/academic/sections", headers=_h(STATE["ptok"])).json()
        assert subs and secs
        STATE["subject_id"] = subs[0]["id"]
        STATE["section_id"] = secs[0]["id"]

    def test_create_assignment(self):
        r = requests.post(f"{API}/assignments", headers=_h(STATE["ptok"]), json={
            "faculty_user_id": STATE["fac_user_id"],
            "subject_id": STATE["subject_id"],
            "section_id": STATE["section_id"],
        })
        assert r.status_code == 201, r.text
        STATE["assignment_id"] = r.json()["id"]

    def test_list_assignment(self):
        r = requests.get(f"{API}/assignments", headers=_h(STATE["ptok"]))
        assert r.status_code == 200

    def test_delete_assignment(self):
        r = requests.delete(f"{API}/assignments/{STATE['assignment_id']}", headers=_h(STATE["ptok"]))
        assert r.status_code == 200


# -------------------------- TIMETABLE + CALENDAR
class TestTimetable:
    def test_create_slot(self):
        r = requests.post(f"{API}/timetable", headers=_h(STATE["ptok"]), json={
            "section_id": STATE["section_id"], "day_of_week": 1, "period": 3,
            "start_time": "09:00", "end_time": "09:45", "label": "Math"
        })
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["updated"] is False
        STATE["slot_id"] = d["id"]

    def test_upsert_same(self):
        r = requests.post(f"{API}/timetable", headers=_h(STATE["ptok"]), json={
            "section_id": STATE["section_id"], "day_of_week": 1, "period": 3,
            "label": "Math-Updated"
        })
        assert r.status_code == 201
        assert r.json()["updated"] is True
        assert r.json()["id"] == STATE["slot_id"]

    def test_list(self):
        r = requests.get(f"{API}/timetable", headers=_h(STATE["ptok"]), params={"section_id": STATE["section_id"]})
        assert r.status_code == 200
        assert any(s["id"] == STATE["slot_id"] for s in r.json())


class TestCalendar:
    def test_create_event(self):
        r = requests.post(f"{API}/calendar", headers=_h(STATE["ptok"]), json={
            "title": "TEST_Holiday", "event_date": "2026-03-15", "kind": "holiday"
        })
        assert r.status_code == 201
        STATE["event_id"] = r.json()["id"]

    def test_list_events(self):
        r = requests.get(f"{API}/calendar", headers=_h(STATE["ptok"]))
        assert r.status_code == 200
        assert any(e["id"] == STATE["event_id"] for e in r.json())

    def test_delete_event(self):
        r = requests.delete(f"{API}/calendar/{STATE['event_id']}", headers=_h(STATE["ptok"]))
        assert r.status_code == 200


# -------------------------- FEES
class TestFees:
    def test_create_structure(self):
        r = requests.post(f"{API}/fees/structures", headers=_h(STATE["ptok"]), json={
            "name": f"TEST_Term_{_rand()}", "amount": 10000.0
        })
        assert r.status_code == 201, r.text
        STATE["struct_id"] = r.json()["id"]

    def test_bulk_assign(self):
        r = requests.post(f"{API}/fees/bulk-assign", headers=_h(STATE["ptok"]), json={
            "structure_id": STATE["struct_id"]
        })
        assert r.status_code == 200, r.text
        assert r.json()["invoices_created"] > 0

    def test_list_invoices(self):
        r = requests.get(f"{API}/fees/invoices", headers=_h(STATE["ptok"]))
        assert r.status_code == 200
        assert len(r.json()) > 0
        STATE["invoice_id"] = r.json()[0]["id"]

    def test_mark_paid(self):
        r = requests.post(f"{API}/fees/invoices/{STATE['invoice_id']}/mark-paid", headers=_h(STATE["ptok"]))
        assert r.status_code == 200
        # verify
        inv = requests.get(f"{API}/fees/invoices", headers=_h(STATE["ptok"])).json()
        target = next(i for i in inv if i["id"] == STATE["invoice_id"])
        assert target["status"] == "paid"
        assert target["amount_paid"] == target["amount"]

    def test_summary(self):
        r = requests.get(f"{API}/fees/summary", headers=_h(STATE["ptok"]))
        assert r.status_code == 200
        assert "by_status" in r.json()


# -------------------------- LIBRARY
class TestLibrary:
    def test_create_book(self):
        r = requests.post(f"{API}/library/books", headers=_h(STATE["ptok"]), json={
            "title": f"TEST_Book_{_rand()}", "author": "A", "total_copies": 2
        })
        assert r.status_code == 201
        STATE["book_id"] = r.json()["id"]
        # verify available_copies = total_copies
        books = requests.get(f"{API}/library/books", headers=_h(STATE["ptok"])).json()
        b = next(x for x in books if x["id"] == STATE["book_id"])
        assert b["available_copies"] == 2

    def test_create_loan(self):
        if not STATE.get("student_id"):
            pytest.skip("no student")
        r = requests.post(f"{API}/library/loans", headers=_h(STATE["ptok"]), json={
            "book_id": STATE["book_id"], "student_id": STATE["student_id"]
        })
        assert r.status_code == 201, r.text
        STATE["loan_id"] = r.json()["id"]
        books = requests.get(f"{API}/library/books", headers=_h(STATE["ptok"])).json()
        b = next(x for x in books if x["id"] == STATE["book_id"])
        assert b["available_copies"] == 1

    def test_no_copies_400(self):
        # take second copy, then try again -> 400
        requests.post(f"{API}/library/loans", headers=_h(STATE["ptok"]), json={
            "book_id": STATE["book_id"], "student_id": STATE["student_id"]
        })
        r = requests.post(f"{API}/library/loans", headers=_h(STATE["ptok"]), json={
            "book_id": STATE["book_id"], "student_id": STATE["student_id"]
        })
        assert r.status_code == 400

    def test_return(self):
        r = requests.post(f"{API}/library/loans/{STATE['loan_id']}/return", headers=_h(STATE["ptok"]))
        assert r.status_code == 200


# -------------------------- TRANSPORT
class TestTransport:
    def test_route(self):
        r = requests.post(f"{API}/transport/routes", headers=_h(STATE["ptok"]), json={
            "name": f"TEST_Route_{_rand()}", "fare_monthly": 500
        })
        assert r.status_code == 201
        STATE["route_id"] = r.json()["id"]

    def test_vehicle(self):
        r = requests.post(f"{API}/transport/vehicles", headers=_h(STATE["ptok"]), json={
            "registration_number": f"TEST-{_rand()}", "capacity": 30, "route_id": STATE["route_id"]
        })
        assert r.status_code == 201

    def test_list(self):
        r = requests.get(f"{API}/transport/routes", headers=_h(STATE["ptok"]))
        assert r.status_code == 200


# -------------------------- HOSTEL
class TestHostel:
    def test_block(self):
        r = requests.post(f"{API}/hostel/blocks", headers=_h(STATE["ptok"]), json={
            "name": f"TEST_Blk_{_rand()}", "kind": "boys"
        })
        assert r.status_code == 201
        STATE["block_id"] = r.json()["id"]

    def test_room(self):
        r = requests.post(f"{API}/hostel/rooms", headers=_h(STATE["ptok"]), json={
            "block_id": STATE["block_id"], "room_number": "101", "capacity": 1
        })
        assert r.status_code == 201
        STATE["room_id"] = r.json()["id"]

    def test_allocation(self):
        if not STATE.get("student_id"):
            pytest.skip("no student")
        r = requests.post(f"{API}/hostel/allocations", headers=_h(STATE["ptok"]), json={
            "student_id": STATE["student_id"], "room_id": STATE["room_id"]
        })
        assert r.status_code == 201, r.text

    def test_full_room_400(self):
        r = requests.post(f"{API}/hostel/allocations", headers=_h(STATE["ptok"]), json={
            "student_id": STATE["student_id"], "room_id": STATE["room_id"]
        })
        assert r.status_code == 400


# -------------------------- PLACEMENTS
class TestPlacements:
    def test_drive(self):
        r = requests.post(f"{API}/placements/drives", headers=_h(STATE["ptok"]), json={
            "company": f"TEST_Co_{_rand()}", "role": "SDE", "package_lpa": 12.5
        })
        assert r.status_code == 201
        STATE["drive_id"] = r.json()["id"]

    def test_offer(self):
        if not STATE.get("student_id"):
            pytest.skip("no student")
        r = requests.post(f"{API}/placements/offers", headers=_h(STATE["ptok"]), json={
            "drive_id": STATE["drive_id"], "student_id": STATE["student_id"], "package_lpa": 12.5
        })
        assert r.status_code == 201, r.text

    def test_summary(self):
        r = requests.get(f"{API}/placements/summary", headers=_h(STATE["ptok"]))
        assert r.status_code == 200
        d = r.json()
        for k in ["drives", "offers", "avg_package_lpa", "top_package_lpa"]:
            assert k in d


# -------------------------- ADMISSIONS (public + admin)
class TestAdmissions:
    def test_public_org(self):
        r = requests.get(f"{API}/public/organization/demo-college")
        assert r.status_code == 200
        assert r.json()["slug"] == "demo-college"

    def test_public_apply(self):
        r = requests.post(f"{API}/public/admissions", json={
            "org_slug": "demo-college",
            "first_name": "TEST_App", "last_name": _rand(),
            "email": f"TEST_app_{_rand()}@x.io", "phone": "9999"
        })
        assert r.status_code == 201, r.text
        STATE["app_id"] = r.json()["id"]

    def test_list_admissions(self):
        r = requests.get(f"{API}/admissions", headers=_h(STATE["ptok"]))
        assert r.status_code == 200
        assert any(a["id"] == STATE["app_id"] for a in r.json())

    def test_update_stage(self):
        r = requests.patch(f"{API}/admissions/{STATE['app_id']}", headers=_h(STATE["ptok"]), json={
            "stage": "reviewed"
        })
        assert r.status_code == 200
        assert r.json()["stage"] == "reviewed"

    def test_enroll(self):
        r = requests.post(f"{API}/admissions/{STATE['app_id']}/enroll", headers=_h(STATE["ptok"]))
        assert r.status_code == 200, r.text
        sid = r.json()["student_id"]
        # verify student exists
        stu = requests.get(f"{API}/students", headers=_h(STATE["ptok"])).json()
        assert any(s["id"] == sid for s in stu)


# -------------------------- REPORTS
class TestReports:
    def test_students_pdf(self):
        r = requests.get(f"{API}/reports/students.pdf", headers=_h(STATE["ptok"]))
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_students_xlsx(self):
        r = requests.get(f"{API}/reports/students.xlsx", headers=_h(STATE["ptok"]))
        assert r.status_code == 200
        assert "spreadsheetml" in r.headers["content-type"]

    def test_attendance_pdf(self):
        r = requests.get(f"{API}/reports/attendance.pdf", headers=_h(STATE["ptok"]), params={"days": 30})
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_marks_pdf(self):
        exams = requests.get(f"{API}/marks/exams", headers=_h(STATE["ptok"]))
        if exams.status_code != 200 or not exams.json():
            pytest.skip("no exams")
        exam_id = exams.json()[0]["id"]
        r = requests.get(f"{API}/reports/marks.pdf", headers=_h(STATE["ptok"]), params={"exam_id": exam_id})
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"


# -------------------------- NOTIFICATIONS SEND
class TestNotifSend:
    def test_send_by_role(self):
        r = requests.post(f"{API}/notifications-send", headers=_h(STATE["ptok"]), json={
            "title": "TEST_Notice", "body": "hi", "role_slug": "faculty"
        })
        assert r.status_code == 201, r.text
        assert r.json()["sent"] >= 1

    def test_send_all_users(self):
        r = requests.post(f"{API}/notifications-send", headers=_h(STATE["ptok"]), json={
            "title": "TEST_Broadcast", "all_users": True
        })
        assert r.status_code == 201
        assert r.json()["sent"] >= 1

    def test_notifications_list(self):
        r = requests.get(f"{API}/notifications", headers=_h(STATE["ftok"]))
        assert r.status_code == 200
        titles = [n["title"] for n in r.json()]
        assert "TEST_Notice" in titles or "TEST_Broadcast" in titles


# -------------------------- MULTI-TENANCY
class TestTenancy:
    def test_new_org_sees_empty(self):
        slug = f"testorg{_rand()}"
        email = f"admin_{_rand()}@t.io"
        r = requests.post(f"{API}/auth/register", json={
            "organization_name": slug, "organization_slug": slug, "org_type": "college",
            "admin_email": email, "admin_password": "Pass@1234",
            "admin_first_name": "A", "admin_last_name": "B",
        })
        assert r.status_code in (200, 201), r.text
        tok = r.json()["access_token"]

        for path in ["/parents", "/timetable", "/calendar", "/fees/invoices",
                     "/library/books", "/transport/routes", "/hostel/blocks",
                     "/placements/drives", "/admissions"]:
            resp = requests.get(f"{API}{path}", headers=_h(tok))
            assert resp.status_code == 200, f"{path}: {resp.text}"
            assert resp.json() == [], f"{path} leaked cross-tenant: {resp.json()}"
