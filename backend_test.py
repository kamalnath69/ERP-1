#!/usr/bin/env python3
"""
Backend API verification script for Athena Education ERP.
Tests core endpoints after PostgreSQL + .env fix.
"""
import os
import sys
import requests
from typing import Dict, Any

# Determine base URL
REACT_APP_BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if REACT_APP_BACKEND_URL:
    BASE_URL = f"{REACT_APP_BACKEND_URL}/api"
    print(f"Using REACT_APP_BACKEND_URL: {BASE_URL}")
else:
    BASE_URL = "http://localhost:8001/api"
    print(f"REACT_APP_BACKEND_URL not set, using fallback: {BASE_URL}")

# Test credentials from /app/memory/test_credentials.md
SUPER_ADMIN = {
    "email": "superadmin@platform.io",
    "password": "Super@123456"
}

PRINCIPAL = {
    "email": "principal@demo-college.edu",
    "password": "Principal@123"
}

# Test results tracking
results = []
tokens = {}


def test(name: str, func):
    """Run a test and track results."""
    try:
        print(f"\n{'='*60}")
        print(f"TEST: {name}")
        print('='*60)
        func()
        results.append({"name": name, "status": "✅ PASS", "error": None})
        print(f"✅ PASS: {name}")
    except AssertionError as e:
        results.append({"name": name, "status": "❌ FAIL", "error": str(e)})
        print(f"❌ FAIL: {name}")
        print(f"   Error: {e}")
    except Exception as e:
        results.append({"name": name, "status": "❌ ERROR", "error": str(e)})
        print(f"❌ ERROR: {name}")
        print(f"   Exception: {e}")


def test_1_health():
    """1. GET /api/health -> expect {"status":"ok"}"""
    r = requests.get(f"{BASE_URL}/health", timeout=10)
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.text}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("status") == "ok", f"Expected status='ok', got {data}"


def test_2_root():
    """2. GET /api/ -> expect service metadata"""
    r = requests.get(f"{BASE_URL}/", timeout=10)
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.text}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert "service" in data or "version" in data, f"Expected service metadata, got {data}"


def test_3_login_super_admin():
    """3. POST /api/auth/login with super admin -> expect tokens + is_super_admin=true"""
    r = requests.post(f"{BASE_URL}/auth/login", json=SUPER_ADMIN, timeout=10)
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.text[:500]}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert "access_token" in data, f"Missing access_token in {data.keys()}"
    assert "refresh_token" in data, f"Missing refresh_token in {data.keys()}"
    assert "user" in data, f"Missing user in {data.keys()}"
    assert data["user"].get("is_super_admin") is True, f"Expected is_super_admin=true, got {data['user']}"
    tokens["super_admin"] = data["access_token"]
    tokens["super_refresh"] = data["refresh_token"]
    print(f"   ✓ Got access_token, refresh_token, is_super_admin=true")


def test_4_login_principal():
    """4. POST /api/auth/login with principal -> expect tokens + user tied to demo-college"""
    r = requests.post(f"{BASE_URL}/auth/login", json=PRINCIPAL, timeout=10)
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.text[:500]}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert "access_token" in data, f"Missing access_token"
    assert "refresh_token" in data, f"Missing refresh_token"
    assert "user" in data, f"Missing user"
    user = data["user"]
    assert user.get("email") == PRINCIPAL["email"], f"Email mismatch"
    # Check organization - could be in user object or nested
    org_id = user.get("organization_id")
    org = user.get("organization")
    assert org_id or org, f"No organization_id or organization in user: {user.keys()}"
    tokens["principal"] = data["access_token"]
    tokens["principal_refresh"] = data["refresh_token"]
    print(f"   ✓ Got tokens, user tied to organization")


def test_5_login_wrong_password():
    """5. Wrong password on either account -> expect 401"""
    # Test super admin with wrong password
    r1 = requests.post(f"{BASE_URL}/auth/login", 
                       json={"email": SUPER_ADMIN["email"], "password": "WrongPassword123"}, 
                       timeout=10)
    print(f"   Super admin wrong password - Status: {r1.status_code}")
    assert r1.status_code == 401, f"Expected 401 for wrong super admin password, got {r1.status_code}"
    
    # Test principal with wrong password
    r2 = requests.post(f"{BASE_URL}/auth/login", 
                       json={"email": PRINCIPAL["email"], "password": "WrongPassword123"}, 
                       timeout=10)
    print(f"   Principal wrong password - Status: {r2.status_code}")
    assert r2.status_code == 401, f"Expected 401 for wrong principal password, got {r2.status_code}"
    print(f"   ✓ Both wrong passwords correctly returned 401")


def test_6_auth_me():
    """6. GET /api/auth/me with principal's bearer token -> expect user object"""
    assert "principal" in tokens, "Principal token not available from test 4"
    headers = {"Authorization": f"Bearer {tokens['principal']}"}
    r = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=10)
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.text[:500]}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert "email" in data or ("user" in data and "email" in data["user"]), f"No email in response: {data.keys()}"
    print(f"   ✓ Got user object")


def test_7_super_admin_organizations():
    """7. GET /api/super-admin/organizations with super admin token -> expect list with demo college"""
    assert "super_admin" in tokens, "Super admin token not available from test 3"
    headers = {"Authorization": f"Bearer {tokens['super_admin']}"}
    r = requests.get(f"{BASE_URL}/super-admin/organizations", headers=headers, timeout=10)
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.text[:500]}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert isinstance(data, list), f"Expected list, got {type(data)}"
    assert len(data) > 0, "Expected at least one organization (demo-college)"
    # Check if demo-college exists
    demo_college = any(
        org.get("slug") == "demo-college" or 
        "demo" in org.get("name", "").lower() or
        "demo-college" in org.get("slug", "")
        for org in data
    )
    assert demo_college, f"demo-college not found in organizations: {[o.get('slug') or o.get('name') for o in data]}"
    print(f"   ✓ Got {len(data)} organizations including demo-college")


def test_8_students():
    """8. GET /api/students with principal token -> expect 200 (list, may be empty)"""
    assert "principal" in tokens, "Principal token not available"
    headers = {"Authorization": f"Bearer {tokens['principal']}"}
    r = requests.get(f"{BASE_URL}/students", headers=headers, timeout=10)
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.text[:500]}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert isinstance(data, list), f"Expected list, got {type(data)}"
    print(f"   ✓ Got {len(data)} students")


def test_9_faculty():
    """9. GET /api/faculty with principal token -> expect 200 with seeded faculty"""
    assert "principal" in tokens, "Principal token not available"
    headers = {"Authorization": f"Bearer {tokens['principal']}"}
    r = requests.get(f"{BASE_URL}/faculty", headers=headers, timeout=10)
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.text[:500]}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert isinstance(data, list), f"Expected list, got {type(data)}"
    print(f"   ✓ Got {len(data)} faculty members")


def test_10_analytics_dashboard():
    """10. GET /api/analytics/dashboard with principal token -> expect 200 KPI payload"""
    assert "principal" in tokens, "Principal token not available"
    headers = {"Authorization": f"Bearer {tokens['principal']}"}
    r = requests.get(f"{BASE_URL}/analytics/dashboard", headers=headers, timeout=10)
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.text[:500]}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert isinstance(data, dict), f"Expected dict, got {type(data)}"
    # Check for KPI-related keys
    expected_keys = ["kpis", "attendance_trend", "department_distribution"]
    found_keys = [k for k in expected_keys if k in data]
    assert len(found_keys) > 0, f"Expected KPI keys {expected_keys}, got {data.keys()}"
    print(f"   ✓ Got analytics dashboard with keys: {list(data.keys())}")


def test_11_students_no_token():
    """11. GET /api/students without token -> expect 401"""
    r = requests.get(f"{BASE_URL}/students", timeout=10)
    print(f"   Status: {r.status_code}")
    assert r.status_code == 401, f"Expected 401 without token, got {r.status_code}: {r.text}"
    print(f"   ✓ Correctly returned 401 without token")


def test_12_auth_refresh():
    """12. POST /api/auth/refresh with valid refresh token -> expect fresh tokens"""
    assert "principal_refresh" in tokens, "Principal refresh token not available"
    r = requests.post(f"{BASE_URL}/auth/refresh", 
                     json={"refresh_token": tokens["principal_refresh"]}, 
                     timeout=10)
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.text[:500]}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert "access_token" in data, f"Missing access_token in refresh response"
    assert "refresh_token" in data, f"Missing refresh_token in refresh response"
    print(f"   ✓ Got fresh access_token and refresh_token")


def main():
    print("\n" + "="*60)
    print("ATHENA EDUCATION ERP - BACKEND API VERIFICATION")
    print("="*60)
    print(f"Base URL: {BASE_URL}")
    print(f"Testing 12 core endpoints after PostgreSQL + .env fix")
    print("="*60)
    
    # Run all tests in order
    test("1. Health endpoint", test_1_health)
    test("2. Root endpoint", test_2_root)
    test("3. Login super admin", test_3_login_super_admin)
    test("4. Login principal", test_4_login_principal)
    test("5. Wrong password returns 401", test_5_login_wrong_password)
    test("6. Auth /me endpoint", test_6_auth_me)
    test("7. Super admin organizations", test_7_super_admin_organizations)
    test("8. Students endpoint", test_8_students)
    test("9. Faculty endpoint", test_9_faculty)
    test("10. Analytics dashboard", test_10_analytics_dashboard)
    test("11. Students without token returns 401", test_11_students_no_token)
    test("12. Auth refresh token", test_12_auth_refresh)
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    passed = sum(1 for r in results if r["status"] == "✅ PASS")
    failed = sum(1 for r in results if r["status"] in ["❌ FAIL", "❌ ERROR"])
    
    for result in results:
        print(f"{result['status']} {result['name']}")
        if result["error"]:
            print(f"     Error: {result['error']}")
    
    print("="*60)
    print(f"Total: {len(results)} | Passed: {passed} | Failed: {failed}")
    print("="*60)
    
    if failed > 0:
        print("\n⚠️  Some tests failed. Check backend logs:")
        print("   tail -n 100 /var/log/supervisor/backend.*.log")
        sys.exit(1)
    else:
        print("\n✅ All tests passed! Backend is fully operational.")
        sys.exit(0)


if __name__ == "__main__":
    main()
