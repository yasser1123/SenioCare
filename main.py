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

import uvicorn
from dotenv import load_dotenv
from google.adk.cli.fast_api import get_fast_api_app

from app.config import SESSION_DB, MEMORY_SERVICE_URI, ALLOWED_ORIGINS, SERVE_WEB_INTERFACE, APP_VERSION, OLLAMA_BASE_URL, OLLAMA_MODEL
from app.openapi import make_custom_openapi
from app.routers import health, sessions, chat_history, user_profile, reports
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

# =============================================================================
# LIFECYCLE — Scheduler
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Start the report generation scheduler and Firebase on app boot."""
    setup_scheduler()
    # Initialize Firebase for push notifications
    try:
        from app.notifications import init_firebase
        init_firebase()
    except Exception as e:
        print(f"[Startup] Firebase init warning: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Gracefully stop the scheduler."""
    shutdown_scheduler()


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

    GET  /health              - Health check
    GET  /docs                - Swagger UI

  Session DB : {db_label}
  Memory     : {mem_label}
  Model      : {OLLAMA_MODEL}
  Ollama     : {OLLAMA_BASE_URL or 'localhost:11434 (local)'}
  Scheduler  : Daily 23:00 | Weekly Sun 23:00 | Monthly 1st 23:00
  Emergency  : Auto-trigger + FCM notification to caregivers
  FCM        : Firebase push notifications enabled
==============================================================
    """)

    uvicorn.run(app, host="0.0.0.0", port=port)
