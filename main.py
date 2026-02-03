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
import warnings
import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from google.adk.cli.fast_api import get_fast_api_app

# Suppress Pydantic schema generation warnings from ADK internals
warnings.filterwarnings("ignore", message=".*Unable to generate pydantic-core schema.*")
warnings.filterwarnings("ignore", message=".*EXPERIMENTAL.*")

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
# FIX: Override OpenAPI schema to avoid Pydantic errors with MCP types
# =============================================================================

def custom_openapi():
    """Generate a custom OpenAPI schema that avoids problematic types."""
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "SenioCare API",
            "description": "AI Healthcare Assistant for Elderly Care",
            "version": "1.0.0"
        },
        "paths": {
            "/list-apps": {
                "get": {
                    "summary": "List Available Agents",
                    "description": "Returns a list of available agent applications",
                    "responses": {
                        "200": {
                            "description": "List of agent names",
                            "content": {
                                "application/json": {
                                    "example": ["seniocare"]
                                }
                            }
                        }
                    }
                }
            },
            "/health": {
                "get": {
                    "summary": "Health Check",
                    "description": "Returns service health status",
                    "responses": {
                        "200": {
                            "description": "Health status",
                            "content": {
                                "application/json": {
                                    "example": {"status": "healthy", "service": "seniocare-api", "version": "1.0.0"}
                                }
                            }
                        }
                    }
                }
            },
            "/apps/{app_name}/users/{user_id}/sessions/{session_id}": {
                "post": {
                    "summary": "Create or Update Session",
                    "description": "Initialize or update a session for a user",
                    "parameters": [
                        {"name": "app_name", "in": "path", "required": True, "schema": {"type": "string", "example": "seniocare"}},
                        {"name": "user_id", "in": "path", "required": True, "schema": {"type": "string", "example": "user_123"}},
                        {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string", "example": "session_abc"}}
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "example": {}
                            }
                        }
                    },
                    "responses": {
                        "200": {"description": "Session created/updated successfully"}
                    }
                }
            },
            "/run_sse": {
                "post": {
                    "summary": "Run Agent",
                    "description": "Send a message to the agent and get a response",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "app_name": {"type": "string", "example": "seniocare"},
                                        "user_id": {"type": "string", "example": "user_123"},
                                        "session_id": {"type": "string", "example": "session_abc"},
                                        "new_message": {
                                            "type": "object",
                                            "properties": {
                                                "role": {"type": "string", "example": "user"},
                                                "parts": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "object",
                                                        "properties": {
                                                            "text": {"type": "string", "example": "مرحبا"}
                                                        }
                                                    }
                                                }
                                            }
                                        },
                                        "streaming": {"type": "boolean", "example": False}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Agent response",
                            "content": {
                                "application/json": {
                                    "example": {"events": [{"type": "agent_response", "content": "..."}]}
                                }
                            }
                        }
                    }
                }
            }
        }
    }

# Override the openapi method to use our custom schema
app.openapi = custom_openapi

# Add custom /docs redirect with helpful message
@app.get("/api-docs")
async def custom_docs():
    """
    Custom API documentation endpoint.
    Redirects to the static API_DOCS.md file for complete documentation.
    """
    return RedirectResponse(url="/")

# Add health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": "seniocare-api",
        "version": "1.0.0"
    }


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
║                    SenioCare API Server                      ║
╠══════════════════════════════════════════════════════════════╣
║  Running on: http://localhost:{port:<5}                      ║
║                                                              ║
║  Endpoints:                                                  ║
║    GET  /list-apps           - List agents                   ║
║    POST /run_sse             - Run agent                     ║
║    GET  /apps/seniocare/...  - Session management            ║
║                                                              ║
║  Web UI: http://localhost:{port:<5}                          ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(app, host="0.0.0.0", port=port)
