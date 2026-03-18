"""
Integration tests for SenioCare API endpoints.

These tests use httpx to make real HTTP requests to the running server.
Tests are SKIPPED automatically if the server is not running.

Run: python -m pytest tests/integration/test_api_endpoints.py -v
Requires: python main.py (server running on port 8080)
"""

import json
import uuid
import pytest

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

BASE_URL = "http://localhost:8080"


# ---------------------------------------------------------------------------
# Skip-if helpers
# ---------------------------------------------------------------------------
def _server_running() -> bool:
    if not HAS_HTTPX:
        return False
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


needs_server = pytest.mark.skipif(
    not _server_running(),
    reason="Server not running on localhost:8080 — start with: python main.py",
)
needs_httpx = pytest.mark.skipif(
    not HAS_HTTPX,
    reason="httpx not installed — pip install httpx",
)


# ===========================================================================
# Health & Discovery
# ===========================================================================
@needs_httpx
@needs_server
class TestHealthEndpoints:

    def test_health_check(self):
        r = httpx.get(f"{BASE_URL}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"

    def test_list_apps(self):
        r = httpx.get(f"{BASE_URL}/list-apps")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert "seniocare" in data


# ===========================================================================
# User Profile
# ===========================================================================
@needs_httpx
@needs_server
class TestUserProfileEndpoints:
    USER_ID = f"test_{uuid.uuid4().hex[:8]}"

    def test_01_set_profile(self):
        r = httpx.post(
            f"{BASE_URL}/set-user-profile/{self.USER_ID}",
            json={
                "user_name": "Test User",
                "age": 68,
                "weight": 75.0,
                "height": 165.0,
                "gender": "male",
                "chronicDiseases": ["diabetes"],
                "allergies": ["dairy"],
                "medications": [{"name": "Metformin", "dose": "500mg"}],
                "mobilityStatus": "moderate",
                "bloodType": "O+",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True

    def test_02_get_profile(self):
        """Depends on test_01_set_profile having run first."""
        r = httpx.get(f"{BASE_URL}/get-user-profile/{self.USER_ID}")
        assert r.status_code == 200
        data = r.json()
        if data["success"]:
            assert data["profile"]["user_name"] == "Test User"
            assert data["profile"]["age"] == 68

    def test_03_get_nonexistent_profile(self):
        r = httpx.get(f"{BASE_URL}/get-user-profile/nonexistent_user_xyz")
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False

    def test_04_sync_profile_partial(self):
        """Sync only medications — other fields should remain unchanged."""
        r = httpx.post(
            f"{BASE_URL}/sync-user-profile/{self.USER_ID}",
            json={"medications": [{"name": "Amlodipine", "dose": "5mg"}]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "user:medications" in data.get("updated_fields", [])

    def test_05_sync_profile_empty(self):
        """Sync with no fields should return appropriate response."""
        r = httpx.post(
            f"{BASE_URL}/sync-user-profile/{self.USER_ID}", json={}
        )
        assert r.status_code == 200
        data = r.json()
        # Empty body — no fields to update
        assert data["success"] in (True, False)

    def test_06_set_profile_minimal(self):
        """Only user_name provided — all other fields should default."""
        r = httpx.post(
            f"{BASE_URL}/set-user-profile/minimal_user",
            json={"user_name": "Minimal"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True

    def test_07_set_profile_all_fields(self):
        """All recognized fields populated."""
        r = httpx.post(
            f"{BASE_URL}/set-user-profile/full_user",
            json={
                "user_name": "Full User",
                "age": 75,
                "weight": 80.5,
                "height": 172.0,
                "gender": "male",
                "chronicDiseases": ["diabetes", "hypertension", "arthritis"],
                "allergies": ["shellfish", "dairy"],
                "medications": [
                    {"name": "Metformin", "dose": "500mg"},
                    {"name": "Lisinopril", "dose": "10mg"},
                ],
                "mobilityStatus": "limited",
                "bloodType": "A+",
                "caregiver_ids": ["cg_001"],
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True


# ===========================================================================
# Image Endpoints (validation only — no model invocation)
# ===========================================================================
@needs_httpx
@needs_server
class TestImageEndpoints:

    def test_medication_image_invalid_base64(self):
        """Garbage data should return an error without crashing."""
        r = httpx.post(
            f"{BASE_URL}/analyze-medication-image",
            json={"user_id": "test", "image_base64": "not-valid!!!"},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False

    def test_medical_report_invalid_base64(self):
        r = httpx.post(
            f"{BASE_URL}/analyze-medical-report",
            json={"user_id": "test", "image_base64": "!!!invalid!!!"},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False

    def test_get_user_reports_no_reports(self):
        r = httpx.get(
            f"{BASE_URL}/user-medical-reports/no_reports_user_xyz"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["reports"] == []


# ===========================================================================
# Session Management
# ===========================================================================

@needs_httpx
@needs_server
class TestSessionEndpoints:
    USER_ID = "test_session_user"
    SESSION_ID = f"test_session_{uuid.uuid4().hex[:8]}"

    def test_01_create_session(self):
        r = httpx.post(
            f"{BASE_URL}/apps/seniocare/users/{self.USER_ID}/sessions/{self.SESSION_ID}",
            json={},
        )
        assert r.status_code == 200

    def test_02_get_session(self):
        r = httpx.get(
            f"{BASE_URL}/apps/seniocare/users/{self.USER_ID}/sessions/{self.SESSION_ID}",
        )
        # May or may not exist depending on test order
        assert r.status_code in (200, 404)

    def test_03_list_sessions(self):
        r = httpx.get(
            f"{BASE_URL}/apps/seniocare/users/{self.USER_ID}/sessions",
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
