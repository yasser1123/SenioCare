"""
Application configuration.

All constants, environment parsing, and shared service instances live here.
Imported by routers and main.py — nothing else should need os.environ directly.
"""

import os
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from dotenv import load_dotenv
from google.adk.sessions import DatabaseSessionService

load_dotenv(override=True)

# =============================================================================
# VERSION
# =============================================================================

APP_VERSION = "3.0.0"
APP_NAME = "seniocare"

# =============================================================================
# SESSION DATABASE URL
# =============================================================================
# ADK's DatabaseSessionService requires the +asyncpg driver prefix.
# asyncpg does NOT support sslmode/channel_binding as URL params — strip them.

_raw_session_url = os.environ.get("SESSION_DB_URL", "")

if _raw_session_url.startswith("postgresql://"):
    _parsed = urlparse(_raw_session_url)
    _clean_params = {
        k: v[0]
        for k, v in parse_qs(_parsed.query).items()
        if k not in ("sslmode", "channel_binding")
    }
    _clean_query = urlencode(_clean_params) if _clean_params else ""
    SESSION_DB = urlunparse(_parsed._replace(
        scheme="postgresql+asyncpg",
        query=_clean_query,
    ))
else:
    SESSION_DB = _raw_session_url or "sqlite+aiosqlite:///./sessions.db"

# =============================================================================
# MEMORY SERVICE
# =============================================================================
# ADK only supports Vertex AI Memory Bank URIs, NOT PostgreSQL.
# Cross-session context is handled via user: prefixed state in session DB.

MEMORY_SERVICE_URI = None

# =============================================================================
# CORS
# =============================================================================

ALLOWED_ORIGINS = [
    "http://localhost",
    "http://localhost:3000",   # React/Next.js dev server
    "http://localhost:8080",   # Common backend port
    "http://localhost:5000",   # Flask
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8080",
    "*",  # TODO: Remove in production, replace with specific backend URL
]

# =============================================================================
# FEATURE FLAGS
# =============================================================================

# Enable web UI for testing (set to False in production)
SERVE_WEB_INTERFACE = True

# =============================================================================
# SHARED SERVICE INSTANCES
# =============================================================================
# Single DatabaseSessionService instance shared by all custom endpoints.
# Reuses the same connection pool as the ADK app.

session_service = DatabaseSessionService(db_url=SESSION_DB)
