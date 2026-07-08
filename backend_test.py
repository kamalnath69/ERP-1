#!/usr/bin/env python3
"""
Backend API Test Suite for Athena Education ERP
Tests all core endpoints with proper authentication flows
"""

import requests
import json
import sys
from typing import Dict, Any, Optional

# Read base URL from frontend .env
BASE_URL = "https://sidebar-lock-1.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
SUPER_ADMIN_CREDS = {
    "email": "superadmin@platform.io",
    "password": "Super@123456"
}

PRINCIPAL_CREDS = {
    "email": "principal@demo-college.edu",
    "password": "Principal@123"
}

WRONG_CREDS = {
    "email": "principal@demo-college.edu",
    "password": "WrongPassword123"
}

# Test results tracking
test_results = []
passed = 0
failed = 0


def log_test(test_num: int, name: str, passed_flag: bool, status_code: Optional[int], 
             response_data: Any, error: Optional[str] = None):
    """Log test result"""
    global passed, failed
    
    result = {
        "test_num": test_num,
        "name": name,
        "passed": passed_flag,
        "status_code": status_code,
        "response": response_data,
        "error": error
    }
    test_results.append(result)
    
    if passed_flag:
        passed += 1
        print(f"✅ Test {test_num}: {name}")
        print(f"   Status: {status_code}")
        if isinstance(response_data, dict):
            print(f"   Response: {json.dumps(response_data, indent=2)[:200]}")
        print()
    else:
        failed += 1
        print(f"❌ Test {test_num}: {name}")
        print(f"   Status: {status_code}")
        print(f"   Error: {error}")
        if response_data:
            print(f"   Response: {response_data}")
        print()


def test_1_health():
    """Test 1: GET /api/health"""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        
        if response.status_code == 200 and isinstance(data, dict) and data.get("status") == "ok":
            log_test(1, "GET /api/health", True, response.status_code, data)
            return True
        else:
            log_test(1, "GET /api/health", False, response.status_code, data, 
                    f"Expected 200 with status:ok, got {response.status_code}")
            return False
    except Exception as e:
        log_test(1, "GET /api/health", False, None, None, str(e))
        return False


def test_2_root():
    """Test 2: GET /api/"""
    try:
        response = requests.get(f"{BASE_URL}/", timeout=10)
        data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        
        if response.status_code == 200:
            log_test(2, "GET /api/ (service metadata)", True, response.status_code, data)
            return True
        else:
            log_test(2, "GET /api/ (service metadata)", False, response.status_code, data,
                    f"Expected 200, got {response.status_code}")
            return False
    except Exception as e:
        log_test(2, "GET /api/ (service metadata)", False, None, None, str(e))
        return False


def test_3_login_super_admin():
    """Test 3: POST /api/auth/login (super admin)"""
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=SUPER_ADMIN_CREDS, timeout=10)
        data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        
        if response.status_code == 200:
            if isinstance(data, dict) and "access_token" in data and "refresh_token" in data:
                user = data.get("user", {})
                is_super = user.get("is_super_admin", False)
                if is_super:
                    log_test(3, "POST /api/auth/login (super admin)", True, response.status_code, 
                            {"has_tokens": True, "is_super_admin": True, "user_email": user.get("email")})
                    return data
                else:
                    log_test(3, "POST /api/auth/login (super admin)", False, response.status_code, data,
                            "User is not marked as super admin")
                    return None
            else:
                log_test(3, "POST /api/auth/login (super admin)", False, response.status_code, data,
                        "Missing access_token or refresh_token")
                return None
        else:
            log_test(3, "POST /api/auth/login (super admin)", False, response.status_code, data,
                    f"Expected 200, got {response.status_code}")
            return None
    except Exception as e:
        log_test(3, "POST /api/auth/login (super admin)", False, None, None, str(e))
        return None


def test_4_login_principal():
    """Test 4: POST /api/auth/login (principal)"""
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=PRINCIPAL_CREDS, timeout=10)
        data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        
        if response.status_code == 200:
            if isinstance(data, dict) and "access_token" in data and "refresh_token" in data:
                user = data.get("user", {})
                org = user.get("organization")
                log_test(4, "POST /api/auth/login (principal)", True, response.status_code,
                        {"has_tokens": True, "user_email": user.get("email"), "org": org})
                return data
            else:
                log_test(4, "POST /api/auth/login (principal)", False, response.status_code, data,
                        "Missing access_token or refresh_token")
                return None
        else:
            log_test(4, "POST /api/auth/login (principal)", False, response.status_code, data,
                    f"Expected 200, got {response.status_code}")
            return None
    except Exception as e:
        log_test(4, "POST /api/auth/login (principal)", False, None, None, str(e))
        return None


def test_5_login_wrong_password():
    """Test 5: POST /api/auth/login (wrong password)"""
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=WRONG_CREDS, timeout=10)
        data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        
        if response.status_code == 401:
            log_test(5, "POST /api/auth/login (wrong password)", True, response.status_code,
                    {"message": "Correctly rejected invalid credentials"})
            return True
        else:
            log_test(5, "POST /api/auth/login (wrong password)", False, response.status_code, data,
                    f"Expected 401, got {response.status_code}")
            return False
    except Exception as e:
        log_test(5, "POST /api/auth/login (wrong password)", False, None, None, str(e))
        return False


def test_6_auth_me(token: str):
    """Test 6: GET /api/auth/me (with principal token)"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=10)
        data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        
        if response.status_code == 200:
            if isinstance(data, dict) and "email" in data:
                log_test(6, "GET /api/auth/me (principal token)", True, response.status_code,
                        {"email": data.get("email"), "role": data.get("role")})
                return True
            else:
                log_test(6, "GET /api/auth/me (principal token)", False, response.status_code, data,
                        "Response missing expected user fields")
                return False
        else:
            log_test(6, "GET /api/auth/me (principal token)", False, response.status_code, data,
                    f"Expected 200, got {response.status_code}")
            return False
    except Exception as e:
        log_test(6, "GET /api/auth/me (principal token)", False, None, None, str(e))
        return False


def test_7_super_admin_orgs(token: str):
    """Test 7: GET /api/super-admin/organizations (super admin token)"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/super-admin/organizations", headers=headers, timeout=10)
        data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        
        if response.status_code == 200:
            if isinstance(data, list):
                log_test(7, "GET /api/super-admin/organizations (super token)", True, response.status_code,
                        {"org_count": len(data), "sample": data[0] if data else None})
                return True
            else:
                log_test(7, "GET /api/super-admin/organizations (super token)", False, response.status_code, data,
                        "Expected list of organizations")
                return False
        else:
            log_test(7, "GET /api/super-admin/organizations (super token)", False, response.status_code, data,
                    f"Expected 200, got {response.status_code}")
            return False
    except Exception as e:
        log_test(7, "GET /api/super-admin/organizations (super token)", False, None, None, str(e))
        return False


def test_8_students(token: str):
    """Test 8: GET /api/students (principal token)"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/students", headers=headers, timeout=10)
        data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        
        if response.status_code == 200:
            log_test(8, "GET /api/students (principal token)", True, response.status_code,
                    {"type": type(data).__name__, "count": len(data) if isinstance(data, list) else "N/A"})
            return True
        else:
            log_test(8, "GET /api/students (principal token)", False, response.status_code, data,
                    f"Expected 200, got {response.status_code}")
            return False
    except Exception as e:
        log_test(8, "GET /api/students (principal token)", False, None, None, str(e))
        return False


def test_9_faculty(token: str):
    """Test 9: GET /api/faculty (principal token)"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/faculty", headers=headers, timeout=10)
        data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        
        if response.status_code == 200:
            log_test(9, "GET /api/faculty (principal token)", True, response.status_code,
                    {"type": type(data).__name__, "count": len(data) if isinstance(data, list) else "N/A"})
            return True
        else:
            log_test(9, "GET /api/faculty (principal token)", False, response.status_code, data,
                    f"Expected 200, got {response.status_code}")
            return False
    except Exception as e:
        log_test(9, "GET /api/faculty (principal token)", False, None, None, str(e))
        return False


def test_10_analytics_dashboard(token: str):
    """Test 10: GET /api/analytics/dashboard (principal token)"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/analytics/dashboard", headers=headers, timeout=10)
        data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        
        if response.status_code == 200:
            log_test(10, "GET /api/analytics/dashboard (principal token)", True, response.status_code,
                    {"type": type(data).__name__})
            return True
        else:
            log_test(10, "GET /api/analytics/dashboard (principal token)", False, response.status_code, data,
                    f"Expected 200, got {response.status_code}")
            return False
    except Exception as e:
        log_test(10, "GET /api/analytics/dashboard (principal token)", False, None, None, str(e))
        return False


def test_11_students_no_auth():
    """Test 11: GET /api/students (no token)"""
    try:
        response = requests.get(f"{BASE_URL}/students", timeout=10)
        data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        
        if response.status_code == 401:
            log_test(11, "GET /api/students (no token)", True, response.status_code,
                    {"message": "Correctly rejected unauthenticated request"})
            return True
        else:
            log_test(11, "GET /api/students (no token)", False, response.status_code, data,
                    f"Expected 401, got {response.status_code}")
            return False
    except Exception as e:
        log_test(11, "GET /api/students (no token)", False, None, None, str(e))
        return False


def test_12_refresh_token(refresh_token: str):
    """Test 12: POST /api/auth/refresh (with valid refresh token)"""
    try:
        response = requests.post(f"{BASE_URL}/auth/refresh", 
                                json={"refresh_token": refresh_token}, timeout=10)
        data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        
        if response.status_code == 200:
            if isinstance(data, dict) and "access_token" in data:
                log_test(12, "POST /api/auth/refresh (valid refresh token)", True, response.status_code,
                        {"has_new_access_token": True})
                return True
            else:
                log_test(12, "POST /api/auth/refresh (valid refresh token)", False, response.status_code, data,
                        "Missing new access_token in response")
                return False
        else:
            log_test(12, "POST /api/auth/refresh (valid refresh token)", False, response.status_code, data,
                    f"Expected 200, got {response.status_code}")
            return False
    except Exception as e:
        log_test(12, "POST /api/auth/refresh (valid refresh token)", False, None, None, str(e))
        return False


def main():
    """Run all tests"""
    print("=" * 80)
    print("ATHENA EDUCATION ERP - BACKEND API TEST SUITE")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print("=" * 80)
    print()
    
    # Test 1: Health check
    test_1_health()
    
    # Test 2: Root endpoint
    test_2_root()
    
    # Test 3: Super admin login
    super_admin_response = test_3_login_super_admin()
    super_admin_token = super_admin_response.get("access_token") if super_admin_response else None
    
    # Test 4: Principal login
    principal_response = test_4_login_principal()
    principal_token = principal_response.get("access_token") if principal_response else None
    principal_refresh = principal_response.get("refresh_token") if principal_response else None
    
    # Test 5: Wrong password
    test_5_login_wrong_password()
    
    # Test 6: Auth me (requires principal token)
    if principal_token:
        test_6_auth_me(principal_token)
    else:
        log_test(6, "GET /api/auth/me (principal token)", False, None, None,
                "Skipped - no principal token from test 4")
    
    # Test 7: Super admin organizations (requires super admin token)
    if super_admin_token:
        test_7_super_admin_orgs(super_admin_token)
    else:
        log_test(7, "GET /api/super-admin/organizations (super token)", False, None, None,
                "Skipped - no super admin token from test 3")
    
    # Test 8: Students (requires principal token)
    if principal_token:
        test_8_students(principal_token)
    else:
        log_test(8, "GET /api/students (principal token)", False, None, None,
                "Skipped - no principal token from test 4")
    
    # Test 9: Faculty (requires principal token)
    if principal_token:
        test_9_faculty(principal_token)
    else:
        log_test(9, "GET /api/faculty (principal token)", False, None, None,
                "Skipped - no principal token from test 4")
    
    # Test 10: Analytics dashboard (requires principal token)
    if principal_token:
        test_10_analytics_dashboard(principal_token)
    else:
        log_test(10, "GET /api/analytics/dashboard (principal token)", False, None, None,
                "Skipped - no principal token from test 4")
    
    # Test 11: Students without auth
    test_11_students_no_auth()
    
    # Test 12: Refresh token (requires refresh token from principal login)
    if principal_refresh:
        test_12_refresh_token(principal_refresh)
    else:
        log_test(12, "POST /api/auth/refresh (valid refresh token)", False, None, None,
                "Skipped - no refresh token from test 4")
    
    # Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total Tests: {passed + failed}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print("=" * 80)
    
    # Save detailed results to file
    with open("/app/backend_test_results.json", "w") as f:
        json.dump({
            "summary": {
                "total": passed + failed,
                "passed": passed,
                "failed": failed
            },
            "tests": test_results
        }, f, indent=2)
    
    print(f"\nDetailed results saved to: /app/backend_test_results.json")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
