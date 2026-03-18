"""
SenioCare API Server
====================
FastAPI entry point for backend integration using ADK's built-in FastAPI support.

Endpoints provided by ADK:
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
# Smart OpenAPI schema — includes custom routes, hides crashing ADK internals
# =============================================================================

def custom_openapi():
    """
    Generate a safe OpenAPI schema.

    ADK injects internal routes whose Pydantic models use private types
    (e.g. MCP / proto-plus) that cause schema generation to crash.
    We build the schema ONLY for our custom endpoints so Swagger UI
    shows a clean, working API documentation page.
    """
    from fastapi.openapi.utils import get_openapi

    # Paths we manage ourselves
    CUSTOM_PATHS = {
        "/health", "/list-apps", "/api-docs", "/export-openapi",
        "/set-user-profile/{user_id}",
        "/get-user-profile/{user_id}",
        "/sync-user-profile/{user_id}",
        "/analyze-medication-image",
        "/analyze-medical-report",
        "/user-medical-reports/{user_id}",
    }

    # ADK paths we document manually (their models crash generation)
    ADK_PATHS_MANUAL = {
        "/run_sse": {
            "post": {
                "tags": ["Agent"],
                "summary": "Run Agent",
                "description": "Send a message to the SenioCare agent and receive a response. Use streaming: false for a single JSON response, or streaming: true for Server-Sent Events.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["app_name", "user_id", "session_id", "new_message"],
                                "properties": {
                                    "app_name": {"type": "string", "example": "seniocare", "description": "Always seniocare"},
                                    "user_id": {"type": "string", "example": "user_123", "description": "The users unique identifier"},
                                    "session_id": {"type": "string", "example": "session_abc", "description": "A unique session ID"},
                                    "new_message": {
                                        "type": "object",
                                        "properties": {
                                            "role": {"type": "string", "enum": ["user"], "example": "user"},
                                            "parts": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "text": {"type": "string", "example": "\u0645\u0631\u062d\u0628\u0627", "description": "The users message text"}
                                                    }
                                                }
                                            }
                                        }
                                    },
                                    "streaming": {"type": "boolean", "example": False, "description": "false = single JSON, true = SSE stream"}
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Agent response with events",
                        "content": {"application/json": {"example": {"events": [{"type": "agent_response", "content": "..."}]}}}
                    }
                }
            }
        },
        "/apps/{app_name}/users/{user_id}/sessions/{session_id}": {
            "post": {
                "tags": ["Sessions"], "summary": "Create Session",
                "description": "Create a new conversation session. Must be called before /run_sse.",
                "parameters": [
                    {"name": "app_name", "in": "path", "required": True, "schema": {"type": "string", "example": "seniocare"}},
                    {"name": "user_id", "in": "path", "required": True, "schema": {"type": "string", "example": "user_123"}},
                    {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string", "example": "session_abc"}}
                ],
                "requestBody": {"content": {"application/json": {"example": {}}}},
                "responses": {"200": {"description": "Session created successfully"}}
            },
            "get": {
                "tags": ["Sessions"], "summary": "Get Session",
                "description": "Retrieve session info and state.",
                "parameters": [
                    {"name": "app_name", "in": "path", "required": True, "schema": {"type": "string", "example": "seniocare"}},
                    {"name": "user_id", "in": "path", "required": True, "schema": {"type": "string", "example": "user_123"}},
                    {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string", "example": "session_abc"}}
                ],
                "responses": {"200": {"description": "Session data"}}
            },
            "delete": {
                "tags": ["Sessions"], "summary": "Delete Session",
                "description": "Delete a specific session.",
                "parameters": [
                    {"name": "app_name", "in": "path", "required": True, "schema": {"type": "string", "example": "seniocare"}},
                    {"name": "user_id", "in": "path", "required": True, "schema": {"type": "string", "example": "user_123"}},
                    {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string", "example": "session_abc"}}
                ],
                "responses": {"200": {"description": "Session deleted"}}
            }
        },
        "/apps/{app_name}/users/{user_id}/sessions": {
            "get": {
                "tags": ["Sessions"], "summary": "List Sessions",
                "description": "List all sessions for a user.",
                "parameters": [
                    {"name": "app_name", "in": "path", "required": True, "schema": {"type": "string", "example": "seniocare"}},
                    {"name": "user_id", "in": "path", "required": True, "schema": {"type": "string", "example": "user_123"}}
                ],
                "responses": {"200": {"description": "List of session IDs"}}
            }
        },
    }

    # Filter app routes to only safe custom ones
    safe_routes = [r for r in app.routes if hasattr(r, "path") and r.path in CUSTOM_PATHS]

    try:
        schema = get_openapi(
            title="SenioCare AI Agent API",
            version="2.0.0",
            description=(
                "AI-powered healthcare assistant API for elderly care.\n\n"
                "## Integration Guide\n"
                "1. **Set user profile** via `/set-user-profile/{user_id}` after registration\n"
                "2. **Create a session** via `POST /apps/seniocare/users/{user_id}/sessions/{session_id}`\n"
                "3. **Send messages** via `POST /run_sse` with the session ID\n"
                "4. **Image analysis** \u2014 upload medication or report images for AI extraction\n\n"
                "## Models Required (Ollama)\n"
                "- Chat: `llama3.1:8b`\n"
                "- Medication OCR: `richardyoung/olmocr2:7b-q8`\n"
                "- Report Analysis: `llama3.2-vision`\n"
            ),
            routes=safe_routes,
        )
    except Exception:
        schema = {
            "openapi": "3.1.0",
            "info": {"title": "SenioCare AI Agent API", "version": "2.0.0"},
            "paths": {},
        }

    # Merge ADK paths that we documented manually
    for path, methods in ADK_PATHS_MANUAL.items():
        schema["paths"][path] = methods

    # Tag ordering for nice display
    schema["tags"] = [
        {"name": "Health", "description": "Service health and discovery"},
        {"name": "User Profile", "description": "Push/pull user health profile data"},
        {"name": "Image Analysis", "description": "AI-powered medication and medical report image analysis"},
        {"name": "Agent", "description": "Send messages to the SenioCare AI agent"},
        {"name": "Sessions", "description": "Conversation session management"},
    ]

    return schema


# Override the openapi method to use our custom schema
app.openapi = custom_openapi

# =============================================================================
# CUSTOM ENDPOINTS
# =============================================================================

@app.get("/api-docs", tags=["Health"])
async def custom_docs():
    """
    Redirect to the interactive Swagger UI documentation.
    """
    return RedirectResponse(url="/docs")


@app.get("/export-openapi", tags=["Health"])
async def export_openapi():
    """
    Export the OpenAPI spec as downloadable JSON.

    Use this to host static Swagger UI docs without deploying the server.
    Save the output to a file and upload to GitHub Pages or SwaggerHub.
    """
    from fastapi.responses import JSONResponse
    return JSONResponse(content=app.openapi(), media_type="application/json")

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for monitoring and uptime checks."""
    return {
        "status": "healthy",
        "service": "seniocare-api",
        "version": "2.0.0",
        "session_db": SESSION_DB,
        "memory_service": "InMemoryMemoryService",
        "docs": "/docs",
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
    """
    Request model for setting user profile data.
    Aligned with backend ElderCreate schema.
    """
    user_name: Optional[str] = None          # Display name (from Firebase, not on Elder)
    age: Optional[int] = None
    weight: Optional[float] = None           # kg
    height: Optional[float] = None           # cm
    gender: Optional[str] = None             # "male" / "female"
    chronicDiseases: List[str] = []          # matches backend ElderCreate.chronicDiseases
    allergies: List[str] = []
    medications: List[MedicationItem] = []   # AI-only (not on Elder model)
    mobilityStatus: Optional[str] = "limited"  # matches backend ElderCreate.mobilityStatus
    bloodType: Optional[str] = None          # e.g. "A+", "O-"
    caregiver_ids: List[str] = []            # linked caregiver IDs

class PartialProfileUpdate(BaseModel):
    """Request model for partial profile sync (only changed fields)."""
    user_name: Optional[str] = None
    age: Optional[int] = None
    weight: Optional[float] = None
    height: Optional[float] = None
    gender: Optional[str] = None
    chronicDiseases: Optional[List[str]] = None
    allergies: Optional[List[str]] = None
    medications: Optional[List[MedicationItem]] = None
    mobilityStatus: Optional[str] = None
    bloodType: Optional[str] = None
    caregiver_ids: Optional[List[str]] = None


@app.post("/set-user-profile/{user_id}", tags=["User Profile"])
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
                "user:weight": profile.weight,
                "user:height": profile.height,
                "user:gender": profile.gender,
                "user:chronicDiseases": profile.chronicDiseases,
                "user:allergies": profile.allergies,
                "user:medications": [m.model_dump() for m in profile.medications],
                "user:mobilityStatus": profile.mobilityStatus,
                "user:bloodType": profile.bloodType,
                "user:caregiver_ids": profile.caregiver_ids,
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
                "user:weight", "user:height", "user:gender",
                "user:chronicDiseases", "user:allergies", "user:medications",
                "user:mobilityStatus", "user:bloodType", "user:caregiver_ids"
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save profile: {str(e)}")


@app.get("/get-user-profile/{user_id}", tags=["User Profile"])
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
            "weight": session.state.get("user:weight"),
            "height": session.state.get("user:height"),
            "gender": session.state.get("user:gender"),
            "chronicDiseases": session.state.get("user:chronicDiseases"),
            "allergies": session.state.get("user:allergies"),
            "medications": session.state.get("user:medications"),
            "mobilityStatus": session.state.get("user:mobilityStatus"),
            "bloodType": session.state.get("user:bloodType"),
            "caregiver_ids": session.state.get("user:caregiver_ids"),
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


@app.post("/sync-user-profile/{user_id}", tags=["User Profile"])
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
        if updates.weight is not None:
            state_updates["user:weight"] = updates.weight
        if updates.height is not None:
            state_updates["user:height"] = updates.height
        if updates.gender is not None:
            state_updates["user:gender"] = updates.gender
        if updates.chronicDiseases is not None:
            state_updates["user:chronicDiseases"] = updates.chronicDiseases
        if updates.allergies is not None:
            state_updates["user:allergies"] = updates.allergies
        if updates.medications is not None:
            state_updates["user:medications"] = [m.model_dump() for m in updates.medications]
        if updates.mobilityStatus is not None:
            state_updates["user:mobilityStatus"] = updates.mobilityStatus
        if updates.bloodType is not None:
            state_updates["user:bloodType"] = updates.bloodType
        if updates.caregiver_ids is not None:
            state_updates["user:caregiver_ids"] = updates.caregiver_ids

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


@app.post("/analyze-medication-image", tags=["Image Analysis"])
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


@app.post("/analyze-medical-report", tags=["Image Analysis"])
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


@app.get("/user-medical-reports/{user_id}", tags=["Image Analysis"])
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
║    POST /analyze-medication-image - Medication OCR (olmocr2) ║
║    POST /analyze-medical-report   - Report analysis (llama3.2)║
║    GET  /user-medical-reports     - Report history           ║
║    GET  /health              - Health check                  ║
║                                                              ║
║  Session DB: {SESSION_DB:<30}                                ║
║  Memory:     InMemoryMemoryService (dev)                     ║
║  Web UI:     http://localhost:{port:<5}                      ║
╚══════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(app, host="0.0.0.0", port=port)
