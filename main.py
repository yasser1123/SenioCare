"""
SenioCare API Server
====================
FastAPI entry point for backend integration using ADK's built-in FastAPI support.

Endpoints provided by ADK:
- GET  /list-apps                                    - List available agents
- POST /apps/{app}/users/{user}/sessions/{session}  - Create/update session
- GET  /apps/{app}/users/{user}/sessions/{session}  - Get session info
- POST /run_sse                                      - Run agent with message

Usage:
    python main.py                    # Runs on port 8080
    python main.py --port 3000        # Custom port

For backend integration:
    POST /run_sse
    {
        "app_name": "seniocare",
        "user_id": "user_123",
        "session_id": "session_abc",
        "new_message": {
            "role": "user",
            "parts": [{"text": "ممكن تقترح عليا وجبة فطار صحية؟"}]
        },
        "streaming": false
    }
"""
import os
import sys
import uvicorn
from google.adk.cli.fast_api import get_fast_api_app

# =============================================================================
# CONFIGURATION
# =============================================================================

# Directory containing agent packages (seniocare/)
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Session storage - SQLite with async driver
SESSION_DB = "sqlite+aiosqlite:///./sessions.db"

# CORS Configuration - Add your backend origins here
ALLOWED_ORIGINS = [
    "http://localhost",
    "http://localhost:3000",   # React/Next.js dev server
    "http://localhost:8080",   # Common backend port
    "http://localhost:5000",   # Flask
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8080",
    "*",  # TODO: Remove in production, add specific backend URL
]

# Enable web UI for testing (set to False in production)
SERVE_WEB_INTERFACE = True

# =============================================================================
# FASTAPI APP
# =============================================================================

app = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_service_uri=SESSION_DB,
    allow_origins=ALLOWED_ORIGINS,
    web=SERVE_WEB_INTERFACE,
)

# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Support custom port via environment or command line
    port = int(os.environ.get("PORT", 8080))
    
    # Allow --port argument
    if "--port" in sys.argv:
        try:
            port_idx = sys.argv.index("--port") + 1
            port = int(sys.argv[port_idx])
        except (IndexError, ValueError):
            pass
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    SenioCare API Server                       ║
╠══════════════════════════════════════════════════════════════╣
║  Running on: http://localhost:{port:<5}                          ║
║                                                              ║
║  Endpoints:                                                  ║
║    GET  /list-apps           - List agents                   ║
║    POST /run_sse             - Run agent                     ║
║    GET  /apps/seniocare/...  - Session management            ║
║                                                              ║
║  Web UI: http://localhost:{port:<5}                              ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(app, host="0.0.0.0", port=port)
