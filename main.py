"""
SenioCare API Server
====================
FastAPI entry point for backend integration using ADK's built-in FastAPI support.

Endpoints provided by ADK (automatically):
- GET  /list-apps                                    - List available agents
- POST /apps/{app}/users/{user}/sessions/{session}  - Create/update session
- GET  /apps/{app}/users/{user}/sessions/{session}  - Get session info
- GET  /apps/{app}/users/{user}/sessions            - List user sessions
- DELETE /apps/{app}/users/{user}/sessions/{session} - Delete session
- POST /run_sse                                      - Run agent with message

Custom endpoints added by SenioCare:
- POST /set-user-profile/{user_id}                  - Push user profile data
- GET  /get-user-profile/{user_id}                  - Get user profile data
- POST /sync-user-profile/{user_id}                 - Sync updated profile
- POST /analyze-medication-image                 - Analyze medication images (OCR)
- POST /analyze-medical-report                    - Analyze medical report images
- GET  /user-medical-reports/{user_id}            - Get user's report history
- GET  /health                                       - Health check

Usage:
    python main.py                    # Runs on port 8080
    python main.py --port 3000        # Custom port
"""
import os
import sys
import json
import warnings
import uvicorn
from fastapi import FastAPI, HTTPException
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

# Session storage - SQLite with async driver (persistent across restarts)
SESSION_DB = "sqlite+aiosqlite:///./sessions.db"

# Memory service - None = InMemoryMemoryService (default, lost on restart)
# For production, use Vertex AI Memory Bank or custom persistent solution
MEMORY_SERVICE_URI = None

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
# FASTAPI APP (ADK-powered)
# =============================================================================

app = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_service_uri=SESSION_DB,
    memory_service_uri=MEMORY_SERVICE_URI,
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
            "version": "2.0.0"
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
                                    "example": {"status": "healthy", "service": "seniocare-api", "version": "2.0.0"}
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
            },
            "/set-user-profile/{user_id}": {
                "post": {
                    "summary": "Set User Profile",
                    "description": "Push user health profile data to persist across all sessions",
                    "parameters": [
                        {"name": "user_id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "example": {
                                    "user_name": "Ahmed",
                                    "age": 72,
                                    "conditions": ["diabetes", "hypertension"],
                                    "allergies": ["shellfish"],
                                    "medications": [{"name": "Metformin", "dose": "500mg"}],
                                    "mobility": "limited"
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {"description": "Profile saved successfully"}
                    }
                }
            },
            "/get-user-profile/{user_id}": {
                "get": {
                    "summary": "Get User Profile",
                    "description": "Retrieve user health profile data stored in session state",
                    "parameters": [
                        {"name": "user_id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {
                        "200": {"description": "User profile data"}
                    }
                }
            },
            "/sync-user-profile/{user_id}": {
                "post": {
                    "summary": "Sync User Profile",
                    "description": "Update user profile data when backend detects changes",
                    "parameters": [
                        {"name": "user_id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "example": {
                                    "medications": [{"name": "Amlodipine", "dose": "5mg"}]
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {"description": "Profile synced successfully"}
                    }
                }
            },
            "/analyze-medication-image": {
                "post": {
                    "summary": "Analyze Medication Image",
                    "description": "Extract medication name, active ingredient, and dose from medication box images using OCR AI (richardyoung/olmocr2:7b-q8). No database storage.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["user_id", "image_base64"],
                                    "properties": {
                                        "user_id": {"type": "string", "example": "user_123"},
                                        "image_base64": {"type": "string", "description": "Base64 encoded image of medication box"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Extracted medication info (name, active ingredient, dosage)"
                        }
                    }
                }
            },
            "/analyze-medical-report": {
                "post": {
                    "summary": "Analyze Medical Report",
                    "description": "Two-pass analysis of medical report images using llama3.2-vision. Extracts lab values, evaluates health situation, classifies severity. Results stored in database.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["user_id", "image_base64"],
                                    "properties": {
                                        "user_id": {"type": "string", "example": "user_123"},
                                        "image_base64": {"type": "string", "description": "Base64 encoded image of medical report"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Full report analysis with health summary and severity"
                        }
                    }
                }
            },
            "/user-medical-reports/{user_id}": {
                "get": {
                    "summary": "Get User Medical Reports",
                    "description": "Retrieve all previously analyzed medical reports for a user",
                    "parameters": [
                        {"name": "user_id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {
                        "200": {"description": "List of analyzed reports"}
                    }
                }
            }
        }
    }

# Override the openapi method to use our custom schema
app.openapi = custom_openapi

# =============================================================================
# CUSTOM ENDPOINTS
# =============================================================================

@app.get("/api-docs")
async def custom_docs():
    """
    Custom API documentation endpoint.
    Redirects to the static API_DOCS.md file for complete documentation.
    """
    return RedirectResponse(url="/")

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": "seniocare-api",
        "version": "2.0.0",
        "session_db": SESSION_DB,
        "memory_service": "InMemoryMemoryService"
    }


# =============================================================================
# USER PROFILE ENDPOINTS
# =============================================================================
# These endpoints allow the backend to push/pull user profile data.
# Data is stored in session state with user: prefix for cross-session persistence.

from pydantic import BaseModel
from typing import Optional, List

class MedicationItem(BaseModel):
    """A single medication entry."""
    name: str
    dose: str

class UserProfileRequest(BaseModel):
    """Request model for setting user profile data."""
    user_name: str
    age: int
    conditions: List[str] = []
    allergies: List[str] = []
    medications: List[MedicationItem] = []
    mobility: str = "limited"  # "limited", "moderate", "active"

class PartialProfileUpdate(BaseModel):
    """Request model for partial profile sync (only changed fields)."""
    user_name: Optional[str] = None
    age: Optional[int] = None
    conditions: Optional[List[str]] = None
    allergies: Optional[List[str]] = None
    medications: Optional[List[MedicationItem]] = None
    mobility: Optional[str] = None


@app.post("/set-user-profile/{user_id}")
async def set_user_profile(user_id: str, profile: UserProfileRequest):
    """
    Push user health profile to persist across all sessions.

    This should be called by the backend:
    - Once after user registration
    - When the user's profile changes (medications, conditions, etc.)

    The data is stored with user: prefix in the session state,
    making it automatically available in ALL sessions for this user.

    Args:
        user_id: The user's unique identifier (from Firebase, etc.)
        profile: The user's health profile data
    """
    from google.adk.sessions import DatabaseSessionService
    import uuid

    # Access the session service from the ADK app internals
    # We need to create/get a session for this user to write state
    try:
        # Get the session service that ADK is using
        session_service = None
        for attr_name in dir(app):
            obj = getattr(app, attr_name, None)
            if isinstance(obj, DatabaseSessionService):
                session_service = obj
                break

        if session_service is None:
            # Fallback: create our own session service with the same DB
            session_service = DatabaseSessionService(db_url=SESSION_DB)

        # Create a temporary session to write user-scoped state
        # ADK will automatically persist user:-prefixed keys for this user_id
        temp_session_id = f"_profile_setup_{uuid.uuid4().hex[:8]}"

        session = await session_service.create_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=temp_session_id,
            state={
                "user:user_id": user_id,
                "user:user_name": profile.user_name,
                "user:age": profile.age,
                "user:conditions": profile.conditions,
                "user:allergies": profile.allergies,
                "user:medications": [m.model_dump() for m in profile.medications],
                "user:mobility": profile.mobility,
            }
        )

        # Clean up the temporary session (the user:-scoped state persists)
        await session_service.delete_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=temp_session_id,
        )

        return {
            "success": True,
            "message": f"Profile saved for user {user_id}",
            "user_id": user_id,
            "profile_keys": [
                "user:user_id", "user:user_name", "user:age",
                "user:conditions", "user:allergies", "user:medications",
                "user:mobility"
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save profile: {str(e)}")


@app.get("/get-user-profile/{user_id}")
async def get_user_profile(user_id: str):
    """
    Get the user's health profile data stored in session state.

    Returns the user:-prefixed state data that was previously set
    via /set-user-profile or populated by the agent callback.

    Args:
        user_id: The user's unique identifier
    """
    from google.adk.sessions import DatabaseSessionService
    import uuid

    try:
        session_service = None
        for attr_name in dir(app):
            obj = getattr(app, attr_name, None)
            if isinstance(obj, DatabaseSessionService):
                session_service = obj
                break

        if session_service is None:
            session_service = DatabaseSessionService(db_url=SESSION_DB)

        # Create a temporary session to read user-scoped state
        temp_session_id = f"_profile_read_{uuid.uuid4().hex[:8]}"
        session = await session_service.create_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=temp_session_id,
        )

        # Read user:-prefixed state (ADK loads these for the user_id)
        profile = {
            "user_id": session.state.get("user:user_id"),
            "user_name": session.state.get("user:user_name"),
            "age": session.state.get("user:age"),
            "conditions": session.state.get("user:conditions"),
            "allergies": session.state.get("user:allergies"),
            "medications": session.state.get("user:medications"),
            "mobility": session.state.get("user:mobility"),
        }

        # Clean up temporary session
        await session_service.delete_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=temp_session_id,
        )

        # Check if profile exists
        if profile["user_id"] is None:
            return {
                "success": False,
                "message": f"No profile found for user {user_id}. Call /set-user-profile first.",
                "profile": None
            }

        return {
            "success": True,
            "user_id": user_id,
            "profile": profile
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get profile: {str(e)}")


@app.post("/sync-user-profile/{user_id}")
async def sync_user_profile(user_id: str, updates: PartialProfileUpdate):
    """
    Sync updated user profile data (partial update).

    Called by the backend when the user's data changes (e.g., doctor changed
    medication, new allergy discovered). Only sends the changed fields.

    Args:
        user_id: The user's unique identifier
        updates: Only the fields that changed (others remain unchanged)
    """
    from google.adk.sessions import DatabaseSessionService
    import uuid

    try:
        session_service = None
        for attr_name in dir(app):
            obj = getattr(app, attr_name, None)
            if isinstance(obj, DatabaseSessionService):
                session_service = obj
                break

        if session_service is None:
            session_service = DatabaseSessionService(db_url=SESSION_DB)

        # Build state update dict with only provided fields
        state_updates = {}
        if updates.user_name is not None:
            state_updates["user:user_name"] = updates.user_name
        if updates.age is not None:
            state_updates["user:age"] = updates.age
        if updates.conditions is not None:
            state_updates["user:conditions"] = updates.conditions
        if updates.allergies is not None:
            state_updates["user:allergies"] = updates.allergies
        if updates.medications is not None:
            state_updates["user:medications"] = [m.model_dump() for m in updates.medications]
        if updates.mobility is not None:
            state_updates["user:mobility"] = updates.mobility

        if not state_updates:
            return {
                "success": False,
                "message": "No fields provided for update"
            }

        # Create a temporary session with the updated state
        temp_session_id = f"_profile_sync_{uuid.uuid4().hex[:8]}"
        session = await session_service.create_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=temp_session_id,
            state=state_updates,
        )

        # Clean up temporary session
        await session_service.delete_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=temp_session_id,
        )

        return {
            "success": True,
            "message": f"Profile synced for user {user_id}",
            "updated_fields": list(state_updates.keys()),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync profile: {str(e)}")


# =============================================================================
# IMAGE ANALYSIS ENDPOINTS
# =============================================================================

class MedicationImageRequest(BaseModel):
    """Request model for medication image analysis."""
    user_id: str
    image_base64: str  # Base64 encoded image of medication box


class MedicalReportRequest(BaseModel):
    """Request model for medical report analysis."""
    user_id: str
    image_base64: str  # Base64 encoded image of medical report


@app.post("/analyze-medication-image")
async def analyze_medication_image_endpoint(request: MedicationImageRequest):
    """
    Analyze a medication box/package image using OCR AI.

    Extracts:
    - Medication name
    - Active ingredient
    - Dose / concentration

    Returns the extracted data directly — no database storage.
    Uses richardyoung/olmocr2:7b-q8 model.
    Run `ollama pull richardyoung/olmocr2:7b-q8` if not installed.
    """
    from seniocare.image_analysis.medication_analyzer import analyze_medication_image
    from seniocare.image_analysis.common import validate_base64_image

    # Validate base64 image
    if not validate_base64_image(request.image_base64):
        return {
            "success": False,
            "error": "Invalid base64 image data"
        }

    result = await analyze_medication_image(
        image_base64=request.image_base64,
        user_id=request.user_id,
    )

    return result.model_dump()


@app.post("/analyze-medical-report")
async def analyze_medical_report_endpoint(request: MedicalReportRequest):
    """
    Analyze a medical report image using vision AI.

    Two-pass analysis:
    1. Extract structured data (lab values, findings, type)
    2. Evaluate health situation and classify severity

    Results are stored in the database for historical tracking.
    Uses llama3.2-vision model.
    Run `ollama pull llama3.2-vision` if not installed.
    """
    from seniocare.image_analysis.report_analyzer import analyze_medical_report
    from seniocare.image_analysis.common import validate_base64_image

    # Validate base64 image
    if not validate_base64_image(request.image_base64):
        return {
            "success": False,
            "error": "Invalid base64 image data"
        }

    result = await analyze_medical_report(
        image_base64=request.image_base64,
        user_id=request.user_id,
    )

    return result.model_dump()


@app.get("/user-medical-reports/{user_id}")
async def get_user_medical_reports(user_id: str):
    """
    Retrieve all previously analyzed medical reports for a user.

    Returns reports ordered by scan date (most recent first).
    """
    from seniocare.image_analysis.report_analyzer import get_user_reports

    reports = get_user_reports(user_id)

    return {
        "success": True,
        "user_id": user_id,
        "count": len(reports),
        "reports": reports,
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
║                    SenioCare API Server v2.0                 ║
╠══════════════════════════════════════════════════════════════╣
║  Running on: http://localhost:{port:<5}                      ║
║                                                              ║
║  ADK Endpoints:                                              ║
║    GET  /list-apps           - List agents                   ║
║    POST /run_sse             - Run agent                     ║
║    POST /apps/seniocare/...  - Session management            ║
║                                                              ║
║  Custom Endpoints:                                           ║
║    POST /set-user-profile    - Push user profile             ║
║    GET  /get-user-profile    - Get user profile              ║
║    POST /sync-user-profile   - Sync profile changes          ║
║    POST /analyze-medication-image - Medication OCR (olmocr2)    ║
║    POST /analyze-medical-report   - Report analysis (llama3.2) ║
║    GET  /user-medical-reports     - Report history              ║
║    GET  /health              - Health check                  ║
║                                                              ║
║  Session DB: {SESSION_DB:<30}           ║
║  Memory:     InMemoryMemoryService (dev)                     ║
║  Web UI:     http://localhost:{port:<5}                      ║
╚══════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(app, host="0.0.0.0", port=port)
