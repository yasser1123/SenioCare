"""
Shared test fixtures for the SenioCare test suite.

Centralizes mock setup, database initialization, and reusable
user profile contexts so individual test files stay clean.

Run all tests:  python -m pytest tests/ -v
Run unit only:  python -m pytest tests/unit/ -v
"""

import os
import sys
import types
import pytest

# ---------------------------------------------------------------------------
# Project root on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Mock google.adk hierarchy BEFORE any seniocare imports
# ---------------------------------------------------------------------------

class MockToolContext:
    """Minimal mock of google.adk.tools.ToolContext for testing."""

    def __init__(self, state: dict = None):
        self.state = state or {}


_mock_google = types.ModuleType("google")
_mock_adk = types.ModuleType("google.adk")
_mock_adk_tools = types.ModuleType("google.adk.tools")
_mock_adk_tools.ToolContext = MockToolContext
_mock_adk_agents = types.ModuleType("google.adk.agents")
_mock_adk_models = types.ModuleType("google.adk.models")
_mock_adk_models_lite_llm = types.ModuleType("google.adk.models.lite_llm")

# Minimal stubs for agent classes
_mock_adk_agents.LlmAgent = type(
    "LlmAgent", (), {"__init__": lambda self, **kw: None}
)
_mock_adk_agents.SequentialAgent = type(
    "SequentialAgent", (), {"__init__": lambda self, **kw: None}
)
_mock_adk_models_lite_llm.LiteLlm = type(
    "LiteLlm", (), {"__init__": lambda self, **kw: None}
)

for name, mod in [
    ("google", _mock_google),
    ("google.adk", _mock_adk),
    ("google.adk.tools", _mock_adk_tools),
    ("google.adk.agents", _mock_adk_agents),
    ("google.adk.models", _mock_adk_models),
    ("google.adk.models.lite_llm", _mock_adk_models_lite_llm),
]:
    sys.modules.setdefault(name, mod)

# Mock pydantic if not installed
try:
    import pydantic  # noqa: F401
except ImportError:
    _mock_pydantic = types.ModuleType("pydantic")

    class _MockBaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)

    _mock_pydantic.BaseModel = _MockBaseModel
    sys.modules.setdefault("pydantic", _mock_pydantic)

# Mock httpx if not installed
try:
    import httpx  # noqa: F401
except ImportError:
    _mock_httpx = types.ModuleType("httpx")
    _mock_httpx.AsyncClient = type(
        "AsyncClient", (), {"__init__": lambda self, **kw: None}
    )
    sys.modules.setdefault("httpx", _mock_httpx)


# ---------------------------------------------------------------------------
# Test database URL check (must happen BEFORE database import)
# ---------------------------------------------------------------------------
_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "")
if _TEST_DB_URL:
    os.environ["APP_DATABASE_URL"] = _TEST_DB_URL

# Now safe to import seniocare modules
from seniocare.data.database import (  # noqa: E402
    DATABASE_URL as _APP_DB_URL,
    get_connection,
    reset_database,
)

# Which database, if any, will the tool tests hit?
#   TEST_DATABASE_URL  -> disposable DB, reset + reseeded once per run (preferred)
#   APP_DATABASE_URL   -> whatever .env points at (read-only queries, but slow and
#                         NOT isolated - fine for local runs, never for CI)
#   neither            -> every DB-backed test is skipped with a clear reason
_DB_AVAILABLE = bool(_TEST_DB_URL or _APP_DB_URL)

# Test modules whose tests all require a live PostgreSQL database. The tools
# under seniocare/tools/ open a connection on every call, so "unit" tests of
# those tools are DB tests in practice.
_DB_TEST_DIRS = ("tests/unit/", "tests/integration/test_multi_tool_flows.py", "tests/test_database_tools.py")


def pytest_collection_modifyitems(config, items):
    if _DB_AVAILABLE:
        return
    skip = pytest.mark.skip(
        reason="No database configured - set TEST_DATABASE_URL (or APP_DATABASE_URL) to run DB-backed tests"
    )
    for item in items:
        rel = str(item.fspath).replace("\\", "/")
        if any(marker in rel for marker in _DB_TEST_DIRS):
            item.add_marker(skip)


# ---------------------------------------------------------------------------
# Database fixture (session-scoped — one DB for the entire test run)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Reset the test database once per run if TEST_DATABASE_URL is provided."""
    if _TEST_DB_URL:
        reset_database()
    yield


# ---------------------------------------------------------------------------
# Reusable user profile fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def diabetic_hypertensive_user():
    """User 001: diabetes + hypertension, shellfish allergy, limited mobility."""
    return MockToolContext(state={
        "user:user_id": "user_001",
        "user:user_name": "Ahmed",
        "user:age": 72,
        "user:chronicDiseases": ["diabetes", "hypertension"],
        "user:allergies": ["shellfish"],
        "user:medications": [
            {"name": "Metformin", "dose": "500mg"},
            {"name": "Lisinopril", "dose": "10mg"},
        ],
        "user:mobilityStatus": "limited",
    })


@pytest.fixture
def heart_disease_user():
    """User 003: heart disease, takes Aspirin + Simvastatin + Warfarin."""
    return MockToolContext(state={
        "user:user_id": "user_003",
        "user:chronicDiseases": ["heart disease"],
        "user:allergies": [],
        "user:medications": [
            {"name": "Aspirin", "dose": "81mg"},
            {"name": "Simvastatin", "dose": "20mg"},
            {"name": "Warfarin", "dose": "5mg"},
        ],
        "user:mobilityStatus": "moderate",
    })


@pytest.fixture
def arthritis_user():
    """User with arthritis, limited mobility."""
    return MockToolContext(state={
        "user:user_id": "user_arthritis",
        "user:chronicDiseases": ["arthritis"],
        "user:allergies": [],
        "user:medications": [],
        "user:mobilityStatus": "limited",
    })


@pytest.fixture
def kidney_disease_user():
    """User with kidney disease, multiple allergies."""
    return MockToolContext(state={
        "user:user_id": "user_kidney",
        "user:chronicDiseases": ["kidney disease"],
        "user:allergies": ["dairy", "gluten"],
        "user:medications": [],
        "user:mobilityStatus": "moderate",
    })


@pytest.fixture
def empty_context():
    """Context with no user data at all."""
    return MockToolContext(state={})


@pytest.fixture
def fresh_context():
    """Factory fixture — creates a fresh MockToolContext each call."""
    def _make(state=None):
        return MockToolContext(state=state or {})
    return _make
