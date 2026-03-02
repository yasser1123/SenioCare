"""
Test script for SenioCare API endpoints.

Tests the new user profile endpoints and session management.
Run: python test_api_endpoints.py

Requires the server to be running: python main.py
"""

import requests
import json
import uuid
import sys

BASE_URL = "http://localhost:8080"

def print_result(name, response):
    """Pretty-print test results."""
    status = "✅" if response.status_code == 200 else "❌"
    print(f"\n{status} {name}")
    print(f"   Status: {response.status_code}")
    try:
        data = response.json()
        print(f"   Response: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}")
    except:
        print(f"   Response: {response.text[:300]}")
    return response.status_code == 200


def test_health():
    """Test health endpoint."""
    r = requests.get(f"{BASE_URL}/health")
    return print_result("GET /health", r)


def test_list_apps():
    """Test list apps endpoint."""
    r = requests.get(f"{BASE_URL}/list-apps")
    return print_result("GET /list-apps", r)


def test_set_user_profile():
    """Test setting a user profile."""
    user_id = "test_user_001"
    r = requests.post(
        f"{BASE_URL}/set-user-profile/{user_id}",
        json={
            "user_name": "Ahmed",
            "age": 72,
            "conditions": ["diabetes", "hypertension"],
            "allergies": ["shellfish"],
            "medications": [
                {"name": "Metformin", "dose": "500mg"},
                {"name": "Lisinopril", "dose": "10mg"},
            ],
            "mobility": "limited",
        },
    )
    return print_result(f"POST /set-user-profile/{user_id}", r)


def test_get_user_profile():
    """Test getting a user profile that was previously set."""
    user_id = "test_user_001"
    r = requests.get(f"{BASE_URL}/get-user-profile/{user_id}")
    success = print_result(f"GET /get-user-profile/{user_id}", r)
    
    if success:
        data = r.json()
        if data.get("success") and data.get("profile"):
            profile = data["profile"]
            assert profile["user_name"] == "Ahmed", f"Expected 'Ahmed', got '{profile['user_name']}'"
            assert profile["age"] == 72, f"Expected 72, got {profile['age']}"
            assert "diabetes" in profile.get("conditions", []), "Missing diabetes in conditions"
            print("   ✅ Profile data verified correctly!")
            return True
        else:
            print("   ⚠️ Profile not found (may need to run set_user_profile first)")
            return False
    return False


def test_get_nonexistent_profile():
    """Test getting a profile that doesn't exist."""
    r = requests.get(f"{BASE_URL}/get-user-profile/nonexistent_user_xyz")
    success = print_result("GET /get-user-profile/nonexistent_user_xyz", r)
    if success:
        data = r.json()
        assert data.get("success") == False, "Should return success=false for nonexistent user"
        print("   ✅ Correctly returned no profile!")
    return success


def test_sync_user_profile():
    """Test partial profile sync (medication change)."""
    user_id = "test_user_001"
    r = requests.post(
        f"{BASE_URL}/sync-user-profile/{user_id}",
        json={
            "medications": [
                {"name": "Metformin", "dose": "500mg"},
                {"name": "Amlodipine", "dose": "5mg"},  # Changed from Lisinopril
            ]
        },
    )
    success = print_result(f"POST /sync-user-profile/{user_id}", r)
    
    if success:
        data = r.json()
        assert "user:medications" in data.get("updated_fields", []), "Should update medications"
        print("   ✅ Partial sync worked!")
    return success


def test_create_session():
    """Test creating a session."""
    user_id = "test_user_001"
    session_id = f"test_session_{uuid.uuid4().hex[:8]}"
    r = requests.post(
        f"{BASE_URL}/apps/seniocare/users/{user_id}/sessions/{session_id}",
        json={},
    )
    success = print_result(f"POST /apps/seniocare/users/{user_id}/sessions/{session_id}", r)
    return success, session_id


def test_run_agent(session_id):
    """Test running the agent with a message."""
    user_id = "test_user_001"
    r = requests.post(
        f"{BASE_URL}/run_sse",
        json={
            "app_name": "seniocare",
            "user_id": user_id,
            "session_id": session_id,
            "new_message": {
                "role": "user",
                "parts": [{"text": "مرحبا"}],
            },
            "streaming": False,
        },
    )
    return print_result("POST /run_sse (message)", r)


def main():
    print("=" * 60)
    print("  SenioCare API Endpoint Tests")
    print("=" * 60)
    print(f"  Server: {BASE_URL}")
    
    # Check if server is running
    try:
        requests.get(f"{BASE_URL}/health", timeout=3)
    except requests.exceptions.ConnectionError:
        print("\n❌ Server is not running! Start it with: python main.py")
        sys.exit(1)
    
    results = []
    
    # Basic endpoints
    results.append(("Health Check", test_health()))
    results.append(("List Apps", test_list_apps()))
    
    # User profile endpoints
    results.append(("Set User Profile", test_set_user_profile()))
    results.append(("Get User Profile", test_get_user_profile()))
    results.append(("Get Nonexistent Profile", test_get_nonexistent_profile()))
    results.append(("Sync User Profile", test_sync_user_profile()))
    
    # Verify sync worked
    results.append(("Get Updated Profile", test_get_user_profile()))
    
    # Session + Agent
    session_result = test_create_session()
    results.append(("Create Session", session_result[0]))
    
    if session_result[0]:
        results.append(("Run Agent", test_run_agent(session_result[1])))
    
    # Summary
    print("\n" + "=" * 60)
    print("  Test Summary")
    print("=" * 60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for name, result in results:
        print(f"  {'✅' if result else '❌'} {name}")
    print(f"\n  Result: {passed}/{total} tests passed")
    print("=" * 60)


if __name__ == "__main__":
    main()
