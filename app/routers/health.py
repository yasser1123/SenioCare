"""Health check router.

GET /health              cheap: config + reachability of the DB and model server
GET /health?probe=full   also sends a one-token completion to the model
"""

import asyncio
import time

import httpx
from fastapi import APIRouter, Query

from app import auth as _auth
from app.config import SESSION_DB, MEMORY_SERVICE_URI, APP_VERSION, MODEL_INFO
from seniocare.model import model_settings, probe_url

router = APIRouter(tags=["Health"])

_PROBE_TIMEOUT_S = 5.0
_COMPLETION_TIMEOUT_S = 30.0


def _check_database() -> dict:
    """SELECT 1 through the pooled connection, on a worker thread."""
    from seniocare.data.database import get_connection, pool_stats

    started = time.perf_counter()
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1 AS ok")
            cur.fetchone()
            cur.close()
        finally:
            conn.close()
        return {
            "ok": True,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "pool": pool_stats(),
        }
    except Exception as e:  # noqa: BLE001 - a health check reports, never raises
        return {
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "error": f"{type(e).__name__}: {e}"[:200],
        }


async def _check_model_reachable() -> dict:
    url = probe_url()
    if url is None:
        return {"ok": None, "detail": "provider-hosted API; no unauthenticated reachability check"}
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S) as client:
            response = await client.get(url)
        return {
            "ok": response.status_code < 500,
            "url": url,
            "http_status": response.status_code,
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "url": url,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "error": f"{type(e).__name__}: {e}"[:200],
        }


async def _check_model_completion() -> dict:
    """One-token completion through the exact settings the agents use."""
    import litellm

    settings = dict(model_settings())
    settings["timeout"] = min(float(settings.get("timeout") or _COMPLETION_TIMEOUT_S), _COMPLETION_TIMEOUT_S)
    settings["max_tokens"] = 1
    started = time.perf_counter()
    try:
        response = await litellm.acompletion(
            messages=[{"role": "user", "content": "ping"}],
            **settings,
        )
        usage = getattr(response, "usage", None)
        return {
            "ok": True,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "model_reported": getattr(response, "model", None),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "error": f"{type(e).__name__}: {e}"[:300],
        }


@router.get("/health")
async def health_check(
    probe: str = Query(
        "basic",
        pattern="^(basic|full)$",
        description="'basic' checks reachability; 'full' also runs a one-token completion",
    ),
):
    """Health check for monitoring and for verifying a remote model server."""
    db_type = "Neon PostgreSQL" if "neon" in SESSION_DB else SESSION_DB.split("://")[0]
    memory_type = (
        "PostgreSQL"
        if MEMORY_SERVICE_URI and "neon" in MEMORY_SERVICE_URI
        else "InMemory"
    )

    db_task = asyncio.to_thread(_check_database)
    model_task = _check_model_reachable()
    checks = {"database": None, "model_server": None}
    checks["database"], checks["model_server"] = await asyncio.gather(db_task, model_task)

    if probe == "full":
        checks["model_completion"] = await _check_model_completion()

    failed = [name for name, result in checks.items() if result and result.get("ok") is False]
    return {
        "status": "healthy" if not failed else "degraded",
        "failed_checks": failed,
        "service": "seniocare-api",
        "version": APP_VERSION,
        "model": MODEL_INFO,
        "auth": _auth.describe(),
        "session_db": db_type,
        "memory_service": memory_type,
        "checks": checks,
        "docs": "/docs",
    }
