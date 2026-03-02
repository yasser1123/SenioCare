"""
================================================================================
                            SENIOCARE ROOT AGENT
                     3-Agent Sequential Pipeline
                  Specialized for Elderly Healthcare
================================================================================

Architecture Overview:
━━━━━━━━━━━━━━━━━━━━━━

This is the main orchestrator for the SenioCare elderly healthcare assistant.
It implements a 3-agent sequential pipeline where user data is provided
by the backend with each request (no data fetching agent needed).

Pipeline Flow (ALLOWED requests):
──────────────────────────────────
    ┌─────────────────────────────────┐
    │  User Prompt + User Data        │
    │  (sent by backend)              │
    └───────────────┬─────────────────┘
                    │
                    ▼
    ┌─────────────────────────────────┐
    │  Agent 1: Orchestrator          │
    │  • Safety check                 │
    │  • Intent classification        │
    │  • User profile analysis        │
    │  • Tool-aware task planning     │
    │  → orchestrator_result          │
    └───────────────┬─────────────────┘
                    │
                    ▼
    ┌─────────────────────────────────┐
    │  Agent 2: Feature Agent         │
    │  • Execute tool calls           │
    │  • Decide best option           │
    │  • Check drug interactions      │
    │  • Fetch recipe / videos        │
    │  • Prepare presentation plan    │
    │  → feature_result               │
    └───────────────┬─────────────────┘
                    │
                    ▼
    ┌─────────────────────────────────┐
    │  Agent 3: Formatter             │
    │  • Format in Egyptian Arabic    │
    │  • Structured templates         │
    │  • Emoji section headers        │
    │  → final_response               │
    └─────────────────────────────────┘

State Management:
━━━━━━━━━━━━━━━━━
State keys use ADK prefix scoping:
• user:  → Persists across all sessions for the same user_id (user profile)
• (none) → Session-scoped, persists within one conversation thread
• temp:  → Single invocation only, discarded after each turn

Session & Memory:
━━━━━━━━━━━━━━━━━
• SessionService: DatabaseSessionService (SQLite) — configured in main.py
• MemoryService: InMemoryMemoryService (default) — auto-saves sessions
• Sessions are managed via ADK endpoints (create, get, list, delete)
• Backend sends user profile on first session; ADK persists via user: keys

================================================================================
"""

from google.adk.agents import SequentialAgent

# Import sub-agents
from seniocare.sub_agents.orchestrator_agent import orchestrator_agent
from seniocare.sub_agents.feature_agent import feature_agent
from seniocare.sub_agents.formatter_agent import formatter_agent

# Also ensure the database is initialized on startup
from seniocare.data.database import reset_database as _init_db
_init_db()


# =============================================================================
# USER DATA CALLBACK
# =============================================================================
# This callback runs before each agent invocation. It has two modes:
#
# 1. PRODUCTION MODE (backend integration):
#    The backend calls POST /set-user-profile/{user_id} ONCE to persist
#    user profile data with user: prefix. On subsequent sessions, ADK
#    automatically loads user:-prefixed state for the same user_id.
#    No action needed here — data is already in state.
#
# 2. TEST MODE (adk web):
#    When using `adk web`, there's no backend. This callback pre-populates
#    the session state with a test user so tools work correctly.
#    Only runs if user:user_id is not set (first message ever).

TEST_USER_PROFILE = {
    "user:user_id": "user_001",
    "user:user_name": "Ahmed",
    "user:age": 72,
    "user:conditions": ["diabetes", "hypertension"],
    "user:allergies": ["shellfish"],
    "user:medications": [
        {"name": "Metformin", "dose": "500mg"},
        {"name": "Lisinopril", "dose": "10mg"},
    ],
    "user:mobility": "limited",
}


async def populate_user_data(callback_context):
    """Ensure user profile data is available in session state.

    For ADK web testing: populates test user data if no user profile exists.
    For production: user data is already persisted via /set-user-profile endpoint
    and ADK loads it automatically for the same user_id.
    """
    state = callback_context.state

    # Check if user profile is already loaded (either from backend or previous session)
    if not state.get("user:user_id"):
        # No user profile found — load test user for development
        for key, value in TEST_USER_PROFILE.items():
            state[key] = value
        print(f"[SenioCare] Test user loaded: {TEST_USER_PROFILE['user:user_name']} "
              f"(conditions: {TEST_USER_PROFILE['user:conditions']}, "
              f"medications: {[m['name'] for m in TEST_USER_PROFILE['user:medications']]})")

    # Track conversation turns (session-scoped, resets per session)
    turn_count = state.get("conversation_turn_count", 0)
    state["conversation_turn_count"] = turn_count + 1


# =============================================================================
# MEMORY AUTO-SAVE CALLBACK
# =============================================================================
# After each agent invocation, save the session to long-term memory.
# This allows the agent to recall past conversations in future sessions
# via the load_memory tool.

async def auto_save_to_memory(callback_context):
    """Auto-save session to long-term memory after each turn.

    This enables cross-session recall — the agent can search past
    conversations to provide more personalized responses.
    """
    try:
        invocation_ctx = callback_context._invocation_context
        memory_service = invocation_ctx.memory_service
        if memory_service:
            session = invocation_ctx.session
            await memory_service.add_session_to_memory(session)
    except Exception as e:
        # Don't break the pipeline if memory save fails
        print(f"[SenioCare] Memory save warning: {e}")


# =============================================================================
# MAIN PIPELINE (ROOT AGENT)
# =============================================================================
# Sequential execution ensures each step has access to outputs from previous steps:
# 1. Orchestrator Agent → orchestrator_result (safety, intent, user analysis, task plan)
# 2. Feature Agent      → feature_result (tool results + decision + presentation plan)
# 3. Formatter Agent    → final_response (Egyptian Arabic formatted response)
#
# Callbacks:
#   before_agent_callback → populate_user_data (load user profile + track turns)
#   after_agent_callback  → auto_save_to_memory (save session for long-term recall)

root_agent = SequentialAgent(
    name="seniocare",
    description="SenioCare Elderly Healthcare Assistant - 3-agent sequential pipeline for safe, personalized health recommendations",
    before_agent_callback=populate_user_data,
    after_agent_callback=auto_save_to_memory,
    sub_agents=[
        orchestrator_agent,  # Step 1: Safety + Intent + Tool-Aware Planning
        feature_agent,       # Step 2: Tool Calling + Decision + Presentation Prep
        formatter_agent,     # Step 3: Format final response in Egyptian Arabic
    ],
)