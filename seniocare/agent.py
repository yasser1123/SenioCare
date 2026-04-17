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
• SessionService: DatabaseSessionService (Neon PostgreSQL) — configured in main.py
• MemoryService: Persistent via cloud DB — auto-saves sessions
• Sessions are managed via ADK endpoints (create, get, list, delete)
• Backend sends user profile on first session; ADK persists via user: keys

================================================================================
"""

import re
from google.adk.agents import SequentialAgent

# Import sub-agents
from seniocare.sub_agents.orchestrator_agent import orchestrator_agent
from seniocare.sub_agents.feature_agent import feature_agent
from seniocare.sub_agents.formatter_agent import formatter_agent

# Also ensure the database is initialized on startup
from seniocare.data.database import _initialize_database as _init_db
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
    "user:user_id": "test_user_001",
    "user:user_name": "Ahmed",
    "user:age": 72,
    "user:weight": 78.0,
    "user:height": 170.0,
    "user:gender": "male",
    "user:chronicDiseases": ["diabetes", "hypertension"],
    "user:allergies": ["shellfish"],
    "user:medications": [
        {"name": "Metformin", "dose": "500mg"},
        {"name": "Lisinopril", "dose": "10mg"},
    ],
    "user:mobilityStatus": "limited",
    "user:bloodType": "A+",
    "user:caregiver_ids": [],
    "user:preferences": {
        "food_likes": [],
        "food_dislikes": [],
        "exercise_likes": [],
        "exercise_dislikes": [],
        "general_likes": [],
        "general_dislikes": [],
    },
}


# Headline mapping: orchestrator intent → Arabic headline with emoji
INTENT_HEADLINES = {
    "meal": "🍽️ توصية وجبة",
    "exercise": "🏃 تمارين رياضية",
    "symptom_assessment": "🩺 تقييم أعراض",
    "medical_qa": "❓ سؤال طبي",
    "emotional": "💚 دعم نفسي",
    "routine": "📋 روتين يومي",
    "preference": "⚙️ تفضيلات المستخدم",
    "image_medication": "📸 تحليل صورة دواء",
    "image_report": "📋 تحليل تقرير طبي",
    "emergency": "🚨 حالة طوارئ",
    "blocked": "⛔ طلب محظور",
}


async def populate_user_data(callback_context):
    """Ensure user profile data is available in session state.

    For ADK web testing: populates test user data if no user profile exists.
    For production: user data is already persisted via /set-user-profile endpoint
    and ADK loads it automatically for the same user_id.

    Also builds a compact conversation history from previous turns and injects
    it into state for the orchestrator's context awareness.
    """
    state = callback_context.state

    # Check if user profile is already loaded (either from backend or previous session)
    if not state.get("user:user_id"):
        # No user profile found — load test user for development
        for key, value in TEST_USER_PROFILE.items():
            state[key] = value
        print(f"[SenioCare] Test user loaded: {TEST_USER_PROFILE['user:user_name']} "
              f"(chronicDiseases: {TEST_USER_PROFILE['user:chronicDiseases']}, "
              f"medications: {[m['name'] for m in TEST_USER_PROFILE['user:medications']]})")

    # Initialize preferences if not set
    if not state.get("user:preferences"):
        state["user:preferences"] = {
            "food_likes": [], "food_dislikes": [],
            "exercise_likes": [], "exercise_dislikes": [],
            "general_likes": [], "general_dislikes": [],
        }

    # Track conversation turns (session-scoped, resets per session)
    turn_count = state.get("conversation_turn_count", 0)
    state["conversation_turn_count"] = turn_count + 1

    # Build compact conversation history from previous turns
    # This gives the orchestrator context for follow-up questions
    try:
        session = callback_context._invocation_context.session
        history_lines = []
        for event in session.events[-12:]:  # Last 12 events (approx 3-4 turns)
            if not hasattr(event, 'content') or not event.content:
                continue
            if not event.content.parts:
                continue
            text = event.content.parts[0].text or ""
            if not text.strip():
                continue

            if event.author == "user":
                # Keep user messages compact (max 200 chars)
                history_lines.append(f"User: {text[:200]}")
            elif event.author == "formatter_agent":
                # Keep agent responses compact (max 200 chars)
                history_lines.append(f"Assistant: {text[:200]}")

        # Only keep last 6 lines (3 exchanges)
        state["conversation_history"] = "\n".join(history_lines[-6:]) if history_lines else "No previous conversation."
    except Exception as e:
        state["conversation_history"] = "No previous conversation."
        print(f"[SenioCare] History building notice: {e}")


# =============================================================================
# MEMORY AUTO-SAVE CALLBACK + HEADLINE GENERATION
# =============================================================================
# After each agent invocation:
# 1. Save the session to long-term memory for cross-session recall
# 2. Generate a conversation headline from the orchestrator's intent
#    (only on the first turn of a new session)

async def auto_save_to_memory(callback_context):
    """Auto-save session to long-term memory and generate headline.

    This callback runs after each complete pipeline execution.
    - Saves session for cross-session recall (via memory service)
    - Generates a headline from the orchestrator's classified intent
      (stored in session state for the /chat-history endpoint)
    """
    state = callback_context.state

    # --- Headline Generation (first turn only) ---
    if state.get("conversation_turn_count") == 1 and not state.get("session_headline"):
        try:
            orchestrator_output = state.get("orchestrator_result", "")

            # Extract intent from orchestrator output using regex
            intent = _extract_intent(orchestrator_output)
            headline = INTENT_HEADLINES.get(intent, "💬 محادثة جديدة")

            # Add a context snippet from the first user message
            session = callback_context._invocation_context.session
            first_user_msg = ""
            for event in session.events:
                if hasattr(event, 'content') and event.content and event.content.parts:
                    if event.author == "user":
                        first_user_msg = event.content.parts[0].text or ""
                        break

            if first_user_msg:
                # Append a short snippet for context (e.g., "🍽️ توصية وجبة — عايز فطار صحي")
                snippet = first_user_msg[:40].strip()
                if len(first_user_msg) > 40:
                    snippet += "..."
                headline = f"{headline} — {snippet}"

            state["session_headline"] = headline
            state["session_preview"] = first_user_msg[:100] if first_user_msg else ""
            print(f"[SenioCare] Headline generated: {headline}")

        except Exception as e:
            state["session_headline"] = "💬 محادثة جديدة"
            print(f"[SenioCare] Headline generation notice: {e}")

    # --- Memory Auto-Save ---
    try:
        invocation_ctx = callback_context._invocation_context
        memory_service = invocation_ctx.memory_service
        if memory_service:
            session = invocation_ctx.session
            await memory_service.add_session_to_memory(session)
    except Exception as e:
        # Don't break the pipeline if memory save fails
        print(f"[SenioCare] Memory save warning: {e}")


def _extract_intent(orchestrator_output: str) -> str:
    """Extract the INTENT value from the orchestrator's structured output.

    The orchestrator outputs text like:
        INTENT: meal
    or
        INTENT: symptom_assessment

    Returns the intent string, or 'unknown' if not found.
    """
    if not orchestrator_output:
        return "unknown"

    # Look for "INTENT: <value>" pattern
    match = re.search(r'INTENT:\s*(\w+)', orchestrator_output)
    if match:
        return match.group(1).lower().strip()

    return "unknown"


# =============================================================================
# MAIN PIPELINE (ROOT AGENT)
# =============================================================================
# Sequential execution ensures each step has access to outputs from previous steps:
# 1. Orchestrator Agent → orchestrator_result (safety, intent, user analysis, task plan)
# 2. Feature Agent      → feature_result (tool results + decision + presentation plan)
# 3. Formatter Agent    → final_response (Egyptian Arabic formatted response)
#
# Callbacks:
#   before_agent_callback → populate_user_data (load user profile + track turns + build history)
#   after_agent_callback  → auto_save_to_memory (save session + generate headline)

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