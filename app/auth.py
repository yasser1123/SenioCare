"""
Authentication and per-user authorisation for every route (AUDIT C-01).

Before this module existed, every endpoint, including ADK's ``/run_sse`` and
``/apps/{app}/users/{user_id}/sessions/…``, accepted any ``user_id`` from any
caller. Health profiles, conversations and reports were readable and
writable by anyone who knew (or guessed) an id.

Design
------
- **Firebase ID tokens.** The Flutter apps already sign users in with
  Firebase, and ``firebase-admin`` is already a dependency for push
  notifications, so ``Authorization: Bearer <id_token>`` is verified with
  ``firebase_admin.auth.verify_id_token``. The verifier is pluggable
  (``set_verifier``) for tests and for other identity providers.
- **Pure ASGI middleware**, not a router dependency, so ADK's own routes are
  covered too. The target ``user_id`` is taken from the path when the route
  has one, otherwise from the JSON body (``user_id`` for ``/run_sse``,
  ``/run``, ``/create-session``, ``/reports/generate``; ``elder_user_id`` +
  ``caregiver_id`` for ``/register-caregiver-fcm``). The body is read once and
  replayed to the app.
- **Rule.** A request may act on ``user_id`` U when the token's ``uid`` is U,
  or when ``uid`` is listed in U's ``user:caregiver_ids`` (the allow-list the
  elder's own profile controls). Being present in ``user:caregivers`` is not
  enough, because a caregiver writes that list themselves when registering a
  push token. Admin-only surfaces (ADK dev UI, debug traces, eval sets,
  ``/metrics``) require ``uid`` in ``ADMIN_UIDS``.
- **Modes.** ``AUTH_MODE=firebase`` enforces all of the above.
  ``AUTH_MODE=off`` disables it (local development, the eval harness in HTTP
  mode) and is announced loudly at startup and in ``/health``. When unset,
  the mode is ``firebase`` if the Firebase service-account file exists and
  ``off`` otherwise.

What this does not do: rate limiting, token revocation checks
(``check_revoked``), or scoping caregivers to *what* they may see. Those are
listed in docs/PLAN.md as follow-ups.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Awaitable, Callable, Optional

from seniocare import observability as obs

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _default_mode() -> str:
    explicit = os.environ.get("AUTH_MODE", "").strip().lower()
    if explicit in ("firebase", "off"):
        return explicit
    # Same default path as app/config.py, resolved here so this module can be
    # imported without the ADK-backed config (tests, tooling).
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cred_path = os.environ.get("FIREBASE_CREDENTIALS_PATH", os.path.join(root, "seniocare-firebase-adminsdk.json"))
    return "firebase" if os.path.exists(cred_path) else "off"


AUTH_MODE = _default_mode()
ADMIN_UIDS = {u.strip() for u in os.environ.get("ADMIN_UIDS", "").split(",") if u.strip()}

PUBLIC_PATHS = {"/", "/health", "/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc", "/list-apps", "/favicon.ico"}
ADMIN_PREFIXES = ("/dev-ui", "/debug/", "/builder/", "/metrics", "/apps/{app}/eval")
_ADMIN_RE = re.compile(r"^/apps/[^/]+/(eval|metrics-info)")

# Routes whose target user is in the path
_PATH_USER_RES = [
    re.compile(r"^/apps/[^/]+/users/(?P<user_id>[^/]+)"),
    re.compile(r"^/(?:chat-history|set-user-profile|get-user-profile|sync-user-profile)/(?P<user_id>[^/]+)"),
    re.compile(r"^/reports/medical/(?P<user_id>[^/]+)$"),
    re.compile(r"^/reports/(?P<user_id>[^/]+)(?:/[^/]+)?$"),
]
# Routes whose target user is in the JSON body
_BODY_USER_PATHS = {"/run_sse", "/run", "/create-session", "/reports/generate", "/register-caregiver-fcm"}
_MAX_BODY_INSPECT = 2 * 1024 * 1024

# ---------------------------------------------------------------------------
# Pluggable verifier and user-state loader
# ---------------------------------------------------------------------------

Verifier = Callable[[str], Awaitable[dict]]
StateLoader = Callable[[str], Awaitable[dict]]


class AuthError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


async def _firebase_verifier(token: str) -> dict:
    import asyncio

    from firebase_admin import auth as fb_auth

    from app.notifications import init_firebase

    if not init_firebase():
        raise AuthError(503, "authentication unavailable: Firebase Admin is not initialised")
    try:
        # verify_id_token is synchronous (may fetch Google's public keys); keep the loop free
        claims = await asyncio.to_thread(fb_auth.verify_id_token, token)
    except Exception as e:  # noqa: BLE001 - expired, malformed, wrong project, …
        raise AuthError(401, f"invalid token: {type(e).__name__}") from e
    return {"uid": claims.get("uid") or claims.get("sub"), "claims": claims}


async def _session_state_loader(user_id: str) -> dict:
    """The elder's user-scoped state (caregiver_ids). Temp-session pattern, like the routers."""
    import uuid

    from app.config import APP_NAME, session_service

    sid = f"_auth_read_{uuid.uuid4().hex[:8]}"
    session = await session_service.create_session(app_name=APP_NAME, user_id=user_id, session_id=sid)
    try:
        return dict(session.state or {})
    finally:
        await session_service.delete_session(app_name=APP_NAME, user_id=user_id, session_id=sid)


_verifier: Verifier = _firebase_verifier
_state_loader: StateLoader = _session_state_loader
_caregiver_cache: dict[str, tuple[float, set[str]]] = {}
CAREGIVER_CACHE_TTL_S = 60.0


def set_verifier(fn: Optional[Verifier]) -> None:
    global _verifier
    _verifier = fn or _firebase_verifier


def set_state_loader(fn: Optional[StateLoader]) -> None:
    global _state_loader, _caregiver_cache
    _state_loader = fn or _session_state_loader
    _caregiver_cache = {}


async def caregiver_ids_of(user_id: str) -> set[str]:
    now = time.monotonic()
    hit = _caregiver_cache.get(user_id)
    if hit and hit[0] > now:
        return hit[1]
    try:
        state = await _state_loader(user_id)
    except Exception as e:  # noqa: BLE001
        obs.emit("auth_state_lookup_failed", user_hash=obs.hash_user_id(user_id), error=f"{type(e).__name__}: {e}"[:120])
        return set()
    ids = {str(x) for x in (state.get("user:caregiver_ids") or [])}
    _caregiver_cache[user_id] = (now + CAREGIVER_CACHE_TTL_S, ids)
    return ids


# ---------------------------------------------------------------------------
# Decision logic (pure)
# ---------------------------------------------------------------------------


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith("/docs/")


def is_admin_path(path: str) -> bool:
    return path.startswith(("/dev-ui", "/debug/", "/builder/", "/metrics")) or bool(_ADMIN_RE.match(path))


def target_user_from_path(path: str) -> Optional[str]:
    if path in ("/reports/generate", "/reports/seed"):
        return None
    for rx in _PATH_USER_RES:
        m = rx.match(path)
        if m:
            return m.group("user_id")
    return None


def target_users_from_body(path: str, body: dict) -> tuple[Optional[str], Optional[str]]:
    """(elder/user id the request acts on, caregiver id when the caller registers as one)"""
    if path == "/register-caregiver-fcm":
        return body.get("elder_user_id"), body.get("caregiver_id")
    if path in _BODY_USER_PATHS:
        return body.get("user_id") or body.get("userId"), None
    return None, None


async def authorise(uid: str, path: str, target_user: Optional[str], caregiver_self: Optional[str]) -> None:
    """Raise AuthError(403) unless `uid` may act on this request."""
    if is_admin_path(path):
        if uid not in ADMIN_UIDS:
            raise AuthError(403, "admin only")
        return
    if path == "/register-caregiver-fcm":
        # A caregiver may register their own device; the elder's allow-list
        # (caregiver_ids) still decides whether they may read anything.
        if caregiver_self and uid == caregiver_self:
            return
        raise AuthError(403, "caregiver_id must match the signed-in user")
    if target_user is None:
        return  # authenticated, no per-user resource (e.g. /run without user_id -> app validates)
    if uid == target_user:
        return
    if uid in await caregiver_ids_of(target_user):
        return
    raise AuthError(403, "not allowed to act on this user")


# ---------------------------------------------------------------------------
# ASGI middleware
# ---------------------------------------------------------------------------


class AuthMiddleware:
    def __init__(self, app, mode: Optional[str] = None):
        self.app = app
        self.mode = (mode or AUTH_MODE).lower()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or self.mode == "off":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "") or ""
        if is_public(path):
            await self.app(scope, receive, send)
            return

        try:
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
            token = _bearer(headers.get("authorization"))
            if not token:
                raise AuthError(401, "missing bearer token")
            identity = await _verifier(token)
            uid = identity.get("uid")
            if not uid:
                raise AuthError(401, "token has no uid")

            target = target_user_from_path(path)
            caregiver_self = None
            body_bytes: Optional[bytes] = None
            if target is None and path in _BODY_USER_PATHS and scope.get("method") in ("POST", "PUT", "PATCH"):
                body_bytes = await _read_body(receive)
                try:
                    body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                except (UnicodeDecodeError, json.JSONDecodeError):
                    body = {}
                target, caregiver_self = target_users_from_body(path, body if isinstance(body, dict) else {})

            await authorise(uid, path, target, caregiver_self)
        except AuthError as e:
            obs.emit("auth_denied", path=path, status=e.status, reason=e.detail)
            await _reject(send, e.status, e.detail)
            return

        scope.setdefault("state", {})["auth_uid"] = uid
        if body_bytes is not None:
            receive = _replay(body_bytes)
        await self.app(scope, receive, send)


def _bearer(header: Optional[str]) -> Optional[str]:
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


async def _read_body(receive) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        chunk = message.get("body", b"")
        total += len(chunk)
        if total > _MAX_BODY_INSPECT:
            raise AuthError(413, "request body too large")
        chunks.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _replay(body: bytes):
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


async def _reject(send, status: int, detail: str) -> None:
    payload = json.dumps({"detail": detail}).encode("utf-8")
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]
    if status == 401:
        headers.append((b"www-authenticate", b"Bearer"))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})


def describe() -> dict[str, Any]:
    return {"mode": AUTH_MODE, "admins": len(ADMIN_UIDS), "public_paths": sorted(PUBLIC_PATHS)}
