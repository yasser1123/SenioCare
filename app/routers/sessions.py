"""Session management router — POST /create-session."""

import uuid

from fastapi import APIRouter, HTTPException

from app.config import session_service
from app.schemas.session import CreateSessionRequest, CreateSessionResponse

router = APIRouter(tags=["Sessions"])


@router.post("/create-session")
async def create_session(request: CreateSessionRequest) -> CreateSessionResponse:
    """
    Create a new conversation session with an auto-generated session ID.

    Call this endpoint before starting a new conversation. The server
    generates a unique session_id and returns it in the response body.
    Use this session_id in subsequent /run_sse calls.
    """
    try:
        session_id = uuid.uuid4().hex

        await session_service.create_session(
            app_name="seniocare",
            user_id=request.user_id,
            session_id=session_id,
        )

        return CreateSessionResponse(
            success=True,
            session_id=session_id,
            user_id=request.user_id,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create session: {e}")
