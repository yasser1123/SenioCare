"""Pydantic schemas for session management endpoints."""

from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    """Request model for creating a new conversation session."""
    user_id: str


class CreateSessionResponse(BaseModel):
    """Response model for session creation."""
    success: bool
    session_id: str
    user_id: str
    app_name: str = "seniocare"
