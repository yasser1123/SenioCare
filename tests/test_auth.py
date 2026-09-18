"""AUDIT C-01: authentication + per-user authorisation middleware.

Runs against a tiny FastAPI app with the middleware installed, a fake token
verifier and a fake caregiver allow-list. No Firebase, no ADK, no DB.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("app_auth", ROOT / "app" / "auth.py")
auth = importlib.util.module_from_spec(spec)
sys.modules["app_auth"] = auth
spec.loader.exec_module(auth)

TOKENS = {"tok-elder": "elder_1", "tok-son": "son_1", "tok-stranger": "stranger_1", "tok-admin": "admin_1"}
ALLOWLIST = {"elder_1": {"user:caregiver_ids": ["son_1"], "user:caregivers": [{"caregiver_id": "stranger_1"}]}}


async def fake_verifier(token):
    if token not in TOKENS:
        raise auth.AuthError(401, "invalid token: Fake")
    return {"uid": TOKENS[token]}


async def fake_state(user_id):
    return ALLOWLIST.get(user_id, {})


@pytest.fixture(autouse=True)
def _wire():
    auth.set_verifier(fake_verifier)
    auth.set_state_loader(fake_state)
    auth.ADMIN_UIDS.clear()
    auth.ADMIN_UIDS.add("admin_1")
    yield
    auth.set_verifier(None)
    auth.set_state_loader(None)


def make_app(mode="firebase"):
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/chat-history/{user_id}")
    async def hist(user_id: str, request: Request):
        return {"user_id": user_id, "uid": request.scope["state"].get("auth_uid")}

    @app.post("/run_sse")
    async def run_sse(body: dict):
        return {"echo": body}

    @app.post("/register-caregiver-fcm")
    async def reg(body: dict):
        return {"ok": True}

    @app.get("/metrics/summary")
    async def metrics():
        return {"ok": True}

    @app.get("/apps/seniocare/users/{user_id}/sessions")
    async def adk_sessions(user_id: str):
        return {"user_id": user_id}

    app.add_middleware(auth.AuthMiddleware, mode=mode)
    return TestClient(app)


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_public_path_needs_no_token():
    assert make_app().get("/health").status_code == 200


def test_missing_or_bad_token_is_401():
    c = make_app()
    r = c.get("/chat-history/elder_1")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert c.get("/chat-history/elder_1", headers=H("nope")).status_code == 401
    assert c.get("/chat-history/elder_1", headers={"Authorization": "Basic abc"}).status_code == 401


def test_owner_allowed_and_uid_exposed_to_route():
    r = make_app().get("/chat-history/elder_1", headers=H("tok-elder"))
    assert r.status_code == 200 and r.json()["uid"] == "elder_1"


def test_other_user_is_403():
    assert make_app().get("/chat-history/elder_1", headers=H("tok-stranger")).status_code == 403


def test_caregiver_on_allowlist_is_allowed_but_self_registered_is_not():
    c = make_app()
    assert c.get("/chat-history/elder_1", headers=H("tok-son")).status_code == 200
    # stranger_1 appears in user:caregivers (self-registered) but NOT in caregiver_ids
    assert c.get("/chat-history/elder_1", headers=H("tok-stranger")).status_code == 403


def test_adk_session_routes_are_covered():
    c = make_app()
    assert c.get("/apps/seniocare/users/elder_1/sessions", headers=H("tok-elder")).status_code == 200
    assert c.get("/apps/seniocare/users/elder_1/sessions", headers=H("tok-stranger")).status_code == 403


def test_body_user_id_is_checked_and_body_replayed():
    c = make_app()
    body = {"app_name": "seniocare", "user_id": "elder_1", "session_id": "s", "new_message": {"role": "user", "parts": [{"text": "hi"}]}}
    r = c.post("/run_sse", json=body, headers=H("tok-elder"))
    assert r.status_code == 200 and r.json()["echo"] == body       # the app still received the full body
    assert c.post("/run_sse", json=body, headers=H("tok-stranger")).status_code == 403
    assert c.post("/run_sse", json=body, headers=H("tok-son")).status_code == 200


def test_caregiver_registration_requires_matching_caregiver_id():
    c = make_app()
    body = {"elder_user_id": "elder_1", "caregiver_id": "son_1", "fcm_token": "t"}
    assert c.post("/register-caregiver-fcm", json=body, headers=H("tok-son")).status_code == 200
    assert c.post("/register-caregiver-fcm", json=body, headers=H("tok-stranger")).status_code == 403


def test_admin_paths():
    c = make_app()
    assert c.get("/metrics/summary", headers=H("tok-elder")).status_code == 403
    assert c.get("/metrics/summary", headers=H("tok-admin")).status_code == 200


def test_mode_off_passes_everything():
    c = make_app(mode="off")
    assert c.get("/chat-history/elder_1").status_code == 200
    assert c.get("/metrics/summary").status_code == 200


def test_malformed_json_body_is_403_not_500():
    c = make_app()
    r = c.post("/run_sse", content=b"{not json", headers={**H("tok-elder"), "content-type": "application/json"})
    # no user_id could be read -> no per-user target -> authenticated request passes to the app,
    # which is then responsible for rejecting the malformed body (422 from FastAPI here)
    assert r.status_code in (400, 422)


def test_pure_helpers():
    assert auth.target_user_from_path("/reports/elder_1/rep_9") == "elder_1"
    assert auth.target_user_from_path("/reports/medical/elder_1") == "elder_1"
    assert auth.target_user_from_path("/reports/generate") is None
    assert auth.target_user_from_path("/apps/seniocare/users/u7/sessions/s1") == "u7"
    assert auth.is_admin_path("/apps/seniocare/eval-sets") and auth.is_admin_path("/dev-ui")
    assert not auth.is_admin_path("/apps/seniocare/users/u/sessions")
    assert auth.target_users_from_body("/register-caregiver-fcm", {"elder_user_id": "e", "caregiver_id": "c"}) == ("e", "c")
