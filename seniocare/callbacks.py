"""
Agent lifecycle callbacks for the SenioCare root agent.

before_agent_callback  → populate_user_data   (profile loader + history builder)
after_agent_callback   → auto_save_to_memory  (memory save + headline generator)
"""

import re

# =============================================================================
# TEST USER (used when no backend has pushed a profile)
# =============================================================================

TEST_USER_PROFILE = {
    "user:user_id":         "test_user_001",
    "user:user_name":       "Ahmed",
    "user:age":             72,
    "user:weight":          78.0,
    "user:height":          170.0,
    "user:gender":          "male",
    "user:chronicDiseases": ["diabetes", "hypertension"],
    "user:allergies":       ["shellfish"],
    "user:medications": [
        {"name": "Metformin",  "dose": "500mg"},
        {"name": "Lisinopril", "dose": "10mg"},
    ],
    "user:mobilityStatus": "limited",
    "user:bloodType":      "A+",
    "user:caregiver_ids":  [],
    "user:preferences": {
        "food_likes":       [],
        "food_dislikes":    [],
        "exercise_likes":   [],
        "exercise_dislikes":[],
        "general_likes":    [],
        "general_dislikes": [],
    },
}

# =============================================================================
# HEADLINE MAPPING
# =============================================================================

INTENT_HEADLINES = {
    "meal":               "🍽️ توصية وجبة",
    "exercise":           "🏃 تمارين رياضية",
    "symptom_assessment": "🩺 تقييم أعراض",
    "medical_qa":         "❓ سؤال طبي",
    "emotional":          "💚 دعم نفسي",
    "routine":            "📋 روتين يومي",
    "preference":         "⚙️ تفضيلات المستخدم",
    "image_medication":   "📸 تحليل صورة دواء",
    "image_report":       "📋 تحليل تقرير طبي",
    "emergency":          "🚨 حالة طوارئ",
    "blocked":            "⛔ طلب محظور",
}

# =============================================================================
# BEFORE-AGENT CALLBACK
# =============================================================================


async def populate_user_data(callback_context):
    """
    Ensure user profile data is available in session state before the pipeline runs.

    Modes:
      - Production: user data is already persisted via /set-user-profile and ADK
        loads it automatically; no action needed.
      - Development (adk web): populates a test user if no profile exists.

    Also builds a compact conversation history from previous turns and injects
    it into state so the Orchestrator has context for follow-up questions.
    """
    state = callback_context.state

    # Load test profile if no real user profile is present
    if not state.get("user:user_id"):
        for key, value in TEST_USER_PROFILE.items():
            state[key] = value
        print(
            f"[SenioCare] Test user loaded: {TEST_USER_PROFILE['user:user_name']} "
            f"(diseases: {TEST_USER_PROFILE['user:chronicDiseases']}, "
            f"meds: {[m['name'] for m in TEST_USER_PROFILE['user:medications']]})"
        )

    # Ensure preferences dict exists
    if not state.get("user:preferences"):
        state["user:preferences"] = {
            "food_likes":       [], "food_dislikes":    [],
            "exercise_likes":   [], "exercise_dislikes":[],
            "general_likes":    [], "general_dislikes": [],
        }

    # Track conversation turns (session-scoped)
    turn_count = state.get("conversation_turn_count", 0)
    state["conversation_turn_count"] = turn_count + 1

    # Build compact conversation history for Orchestrator context
    try:
        session = callback_context._invocation_context.session
        history_lines = []
        for event in session.events[-12:]:  # last ~3-4 turns
            if not hasattr(event, "content") or not event.content:
                continue
            if not event.content.parts:
                continue
            text = event.content.parts[0].text or ""
            if not text.strip():
                continue

            if event.author == "user":
                history_lines.append(f"User: {text[:200]}")
            elif event.author == "formatter_agent":
                history_lines.append(f"Assistant: {text[:200]}")

        state["conversation_history"] = (
            "\n".join(history_lines[-6:]) if history_lines else "No previous conversation."
        )
    except Exception as e:
        state["conversation_history"] = "No previous conversation."
        print(f"[SenioCare] History building notice: {e}")


# =============================================================================
# AFTER-AGENT CALLBACK
# =============================================================================


async def auto_save_to_memory(callback_context):
    """
    After each complete pipeline execution:
      1. Generate a conversation headline (first turn only) from the orchestrator's intent.
      2. Save the session to long-term memory for cross-session recall.
    """
    state = callback_context.state

    # --- Headline generation (first turn only) ---
    if state.get("conversation_turn_count") == 1 and not state.get("session_headline"):
        try:
            orchestrator_output = state.get("orchestrator_result", "")
            intent = _extract_intent(orchestrator_output)
            headline = INTENT_HEADLINES.get(intent, "💬 محادثة جديدة")

            session = callback_context._invocation_context.session
            first_user_msg = ""
            for event in session.events:
                if hasattr(event, "content") and event.content and event.content.parts:
                    if event.author == "user":
                        first_user_msg = event.content.parts[0].text or ""
                        break

            if first_user_msg:
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

    # --- Memory auto-save ---
    try:
        invocation_ctx = callback_context._invocation_context
        memory_service = invocation_ctx.memory_service
        if memory_service:
            session = invocation_ctx.session
            await memory_service.add_session_to_memory(session)
    except Exception as e:
        print(f"[SenioCare] Memory save warning: {e}")


# =============================================================================
# HELPERS
# =============================================================================


def _extract_intent(orchestrator_output: str) -> str:
    """Extract the INTENT value from the orchestrator's structured text output."""
    if not orchestrator_output:
        return "unknown"
    match = re.search(r"INTENT:\s*(\w+)", orchestrator_output)
    if match:
        return match.group(1).lower().strip()
    return "unknown"
