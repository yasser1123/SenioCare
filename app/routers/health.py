"""Health check router."""

from fastapi import APIRouter
from app.config import SESSION_DB, MEMORY_SERVICE_URI, APP_VERSION

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """Health check endpoint for monitoring and uptime checks."""
    db_type = "Neon PostgreSQL" if "neon" in SESSION_DB else SESSION_DB.split("://")[0]
    memory_type = (
        "PostgreSQL"
        if MEMORY_SERVICE_URI and "neon" in MEMORY_SERVICE_URI
        else "InMemory"
    )
    return {
        "status": "healthy",
        "service": "seniocare-api",
        "version": APP_VERSION,
        "session_db": db_type,
        "memory_service": memory_type,
        "docs": "/docs",
    }
