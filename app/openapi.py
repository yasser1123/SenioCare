"""
Custom OpenAPI schema generator.

ADK injects internal routes whose Pydantic models use private types
(e.g. MCP / proto-plus) that crash schema generation.
We build the schema ONLY for our custom endpoints so Swagger UI
shows a clean, working documentation page.
"""

from fastapi.openapi.utils import get_openapi

# Paths we own and document automatically via FastAPI
_CUSTOM_PATHS = {
    "/health",
    "/list-apps",
    "/create-session",
    "/chat-history/{user_id}",
    "/chat-history/{user_id}/{session_id}",
    "/set-user-profile/{user_id}",
    "/get-user-profile/{user_id}",
    "/sync-user-profile/{user_id}",
    "/analyze-medication-image",
    "/analyze-medical-report",
    "/user-medical-reports/{user_id}",
}

# ADK paths we document manually (their models crash schema generation)
_ADK_PATHS_MANUAL = {
    "/run_sse": {
        "post": {
            "tags": ["Agent"],
            "summary": "Run Agent",
            "description": (
                "Send a message to the SenioCare agent and receive a response. "
                "Use streaming: false for a single JSON response, "
                "or streaming: true for Server-Sent Events."
            ),
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["app_name", "user_id", "session_id", "new_message"],
                            "properties": {
                                "app_name":    {"type": "string", "example": "seniocare"},
                                "user_id":     {"type": "string", "example": "user_123"},
                                "session_id":  {"type": "string", "example": "session_abc"},
                                "new_message": {
                                    "type": "object",
                                    "properties": {
                                        "role": {"type": "string", "enum": ["user"]},
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
                                "streaming": {"type": "boolean", "example": False},
                            }
                        }
                    }
                }
            },
            "responses": {
                "200": {
                    "description": "Agent response with events",
                    "content": {
                        "application/json": {
                            "example": {"events": [{"type": "agent_response", "content": "..."}]}
                        }
                    }
                }
            }
        }
    },
    "/apps/{app_name}/users/{user_id}/sessions/{session_id}": {
        "post": {
            "tags": ["Sessions"],
            "summary": "Create Session (ADK)",
            "description": "Create a new conversation session via ADK. Prefer POST /create-session (auto-generates session ID).",
            "parameters": [
                {"name": "app_name",    "in": "path", "required": True, "schema": {"type": "string", "example": "seniocare"}},
                {"name": "user_id",     "in": "path", "required": True, "schema": {"type": "string", "example": "user_123"}},
                {"name": "session_id",  "in": "path", "required": True, "schema": {"type": "string", "example": "session_abc"}},
            ],
            "requestBody": {"content": {"application/json": {"example": {}}}},
            "responses": {"200": {"description": "Session created successfully"}}
        },
        "get": {
            "tags": ["Sessions"],
            "summary": "Get Session",
            "description": "Retrieve session info and state.",
            "parameters": [
                {"name": "app_name",   "in": "path", "required": True, "schema": {"type": "string", "example": "seniocare"}},
                {"name": "user_id",    "in": "path", "required": True, "schema": {"type": "string", "example": "user_123"}},
                {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string", "example": "session_abc"}},
            ],
            "responses": {"200": {"description": "Session data"}}
        },
        "delete": {
            "tags": ["Sessions"],
            "summary": "Delete Session",
            "description": "Delete a specific session.",
            "parameters": [
                {"name": "app_name",   "in": "path", "required": True, "schema": {"type": "string", "example": "seniocare"}},
                {"name": "user_id",    "in": "path", "required": True, "schema": {"type": "string", "example": "user_123"}},
                {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string", "example": "session_abc"}},
            ],
            "responses": {"200": {"description": "Session deleted"}}
        },
    },
    "/apps/{app_name}/users/{user_id}/sessions": {
        "get": {
            "tags": ["Sessions"],
            "summary": "List Sessions",
            "description": "List all sessions for a user.",
            "parameters": [
                {"name": "app_name", "in": "path", "required": True, "schema": {"type": "string", "example": "seniocare"}},
                {"name": "user_id",  "in": "path", "required": True, "schema": {"type": "string", "example": "user_123"}},
            ],
            "responses": {"200": {"description": "List of session IDs"}}
        }
    },
}

_TAG_ORDER = [
    {"name": "Health",          "description": "Service health and discovery"},
    {"name": "Sessions",        "description": "Conversation session management"},
    {"name": "Chat History",    "description": "Conversation history with headlines"},
    {"name": "User Profile",    "description": "Push/pull user health profile data"},
    {"name": "Image Analysis",  "description": "AI-powered medication and medical report image analysis"},
    {"name": "Agent",           "description": "Send messages to the SenioCare AI agent"},
]


def make_custom_openapi(app):
    """Return a custom_openapi() closure bound to the given FastAPI app."""

    def custom_openapi():
        safe_routes = [
            r for r in app.routes
            if hasattr(r, "path") and r.path in _CUSTOM_PATHS
        ]

        try:
            schema = get_openapi(
                title="SenioCare AI Agent API",
                version="3.0.0",
                description="AI-powered healthcare assistant API for elderly care.",
                routes=safe_routes,
            )
        except Exception:
            schema = {
                "openapi": "3.1.0",
                "info": {"title": "SenioCare AI Agent API", "version": "3.0.0"},
                "paths": {},
            }

        for path, methods in _ADK_PATHS_MANUAL.items():
            schema["paths"][path] = methods

        schema["tags"] = _TAG_ORDER
        return schema

    return custom_openapi
