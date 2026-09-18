"""
SenioCare API Server
====================
FastAPI entry point. All route logic lives in app/routers/.
All configuration lives in app/config.py.

Usage:
    python main.py               # Runs on port 8080
    python main.py --port 3000   # Custom port
"""

import os
import sys
import warnings
from contextlib import asynccontextmanager

import time

import uvicorn
from dotenv import load_dotenv
from fastapi import Request
from google.adk.cli.fast_api import get_fast_api_app

from seniocare import observability as obs

# JSON logging must be configured before anything else logs.
obs.configure_logging()

from app.config import SESSION_DB, MEMORY_SERVICE_URI, ALLOWED_ORIGINS, SERVE_WEB_INTERFACE, APP_VERSION, MODEL_INFO
from app.openapi import make_custom_openapi
from app.routers import health, sessions, chat_history, user_profile, reports, metrics
from app.scheduler import setup_scheduler, shutdown_scheduler

load_dotenv(override=True)

# Suppress Pydantic schema warnings from ADK internals
warnings.filterwarnings("ignore", message=".*Unable to generate pydantic-core schema.*")
warnings.filterwarnings("ignore", message=".*EXPERIMENTAL.*")

# =============================================================================
# APP
# =============================================================================

# AGENT_DIR must point to the directory that contains the seniocare/ package
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

app = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_service_uri=SESSION_DB,
    memory_service_uri=MEMORY_SERVICE_URI,
    allow_origins=ALLOWED_ORIGINS,
    web=SERVE_WEB_INTERFACE,
)

# Custom OpenAPI schema (keeps Swagger UI clean — ADK routes crash generation)
app.openapi = make_custom_openapi(app)

# =============================================================================
# ROUTERS
# =============================================================================

app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(chat_history.router)
app.include_router(user_profile.router)
app.include_router(reports.router)
app.include_router(metrics.router)

# =============================================================================
# OBSERVABILITY — trace id + request latency (Point C in docs/INSTRUMENTATION.md)
# =============================================================================

_UNTRACED_PATHS = ("/docs", "/openapi.json", "/redoc", "/static", "/dev-ui", "/favicon.ico")


@app.middleware("http")
async def trace_requests(request: Request, call_next):
    """Give every request a trace_id (honouring an incoming X-Trace-Id) and record its latency."""
    trace_id = request.headers.get("x-trace-id") or obs.new_trace_id()
    token = obs.set_trace_id(trace_id)
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Trace-Id"] = trace_id
        return response
    finally:
        path = request.url.path
        if not path.startswith(_UNTRACED_PATHS):
            obs.emit(
                "http_request",
                method=request.method,
                path=path,
                status=status,
                ok=status < 500,
                latency_ms=round((time.perf_counter() - started) * 1000),
            )
        obs.reset_trace_id(token)

# =============================================================================
# LIFECYCLE
# =============================================================================
# ADK's get_fast_api_app() installs its own lifespan. Starlette ignores
# @app.on_event("startup"/"shutdown") handlers whenever a lifespan is set, so
# the previous handlers here NEVER ran: the scheduler was never started and
# Firebase was never initialised in the running app (docs/FINDINGS.md F-02).
# Wrap ADK's lifespan instead of registering event handlers next to it.

_adk_lifespan = app.router.lifespan_context


@asynccontextmanager
async def _lifespan(application):
    async with _adk_lifespan(application):
        obs.start_postgres_sink()
        setup_scheduler()
        try:
            from app.notifications import init_firebase

            init_firebase()
        except Exception as e:  # noqa: BLE001
            print(f"[Startup] Firebase init warning: {e}")
        try:
            yield
        finally:
            shutdown_scheduler()
            obs.stop_postgres_sink()
            try:
                from seniocare.data.database import close_pool

                close_pool()
            except Exception as e:  # noqa: BLE001
                print(f"[Shutdown] pool close warning: {e}")


app.router.lifespan_context = _lifespan


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))

    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except (IndexError, ValueError):
            pass

    db_label  = "Neon PostgreSQL" if "neon" in SESSION_DB else SESSION_DB.split("://")[0]
    mem_label = "PostgreSQL" if MEMORY_SERVICE_URI and "neon" in str(MEMORY_SERVICE_URI) else "InMemory"

    print(f"""
==============================================================
                  SenioCare API Server v{APP_VERSION}
==============================================================
  Running on: http://localhost:{port}

  ADK Endpoints:
    GET  /list-apps           - List agents
    POST /run_sse             - Run agent
    POST /apps/seniocare/...  - Session management (ADK)

  Custom Endpoints:
    POST /create-session           - Create session (auto ID)
    GET  /chat-history/{{user_id}}   - Conversation list
    GET  /chat-history/{{user_id}}/{{session_id}} - Full turns
    POST /set-user-profile/{{user_id}}  - Push user profile
    GET  /get-user-profile/{{user_id}}  - Get user profile
    POST /sync-user-profile/{{user_id}} - Sync profile changes
    POST /register-caregiver-fcm     - Register caregiver FCM token
    POST /reports/generate          - Generate health report
    GET  /reports/{{user_id}}          - List user reports
    GET  /reports/{{user_id}}/{{report_id}} - Report detail
    GET  /reports/medical/{{user_id}}   - Medical image reports

    GET  /health              - Health check (?probe=full to call the model)
    GET  /metrics/summary     - Latency / tokens / cost / routing, last N hours
    GET  /docs                - Swagger UI

  Model      : {MODEL_INFO['model']}  ({MODEL_INFO['location']})
  Model URL  : {MODEL_INFO['api_base'] or 'provider default'}
  Session DB : {db_label}
  Memory     : {mem_label}
  Scheduler  : Daily 23:00 | Weekly Sun 23:00 | Monthly 1st 23:00
  Emergency  : Auto-trigger + FCM notification to caregivers
  FCM        : Firebase push notifications enabled
==============================================================
    """)

    uvicorn.run(app, host="0.0.0.0", port=port)
