"""
Agent lifecycle callbacks for the SenioCare root agent.

before_agent_callback  → populate_user_data   (profile loader + history builder)
after_agent_callback   → auto_save_to_memory  (memory save + headline generator + emergency report trigger)
"""

import asyncio
import re
from datetime import datetime

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
    "user:caregivers": [
        {
            "caregiver_id": "cg_test_001",
            "name": "محمد (ابن)",
            "relationship": "son",
            "fcm_token": "test_fcm_token_placeholder",
        }
    ],
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

    # Ensure caregivers list exists
    if not state.get("user:caregivers"):
        state["user:caregivers"] = []

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
      2. Auto-trigger emergency report if EMERGENCY was detected.
      3. Save the session to long-term memory for cross-session recall.
    """
    state = callback_context.state

    # --- Headline generation (first turn only) ---
    orchestrator_output = state.get("orchestrator_result", "")
    intent = _extract_intent(orchestrator_output)

    if state.get("conversation_turn_count") == 1 and not state.get("session_headline"):
        try:
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

    # --- Emergency report auto-trigger ---
    if intent == "emergency":
        await _trigger_emergency_report(state, orchestrator_output)

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


async def _trigger_emergency_report(state: dict, orchestrator_output: str) -> None:
    """Auto-trigger an emergency report when the orchestrator detects an emergency.

    Runs in the background so it doesn't block the user's chat response.
    The user immediately sees the emergency guidance from the Formatter,
    while the report is generated, stored, and caregivers are notified
    asynchronously.
    """
    try:
        user_id = state.get("user:user_id", "unknown")
        user_name = state.get("user:user_name", "المستخدم")
        caregivers = state.get("user:caregivers", []) or []

        # Extract the user's message that triggered the emergency
        emergency_message = orchestrator_output[:500]

        emergency_context = {
            "emergency_events": [{
                "trigger": "chat_emergency_detected",
                "message": emergency_message,
                "timestamp": datetime.now().isoformat(),
            }],
            "conversation_topics": state.get("conversation_history", "").split("\n"),
        }

        # Fire-and-forget background task
        asyncio.create_task(
            _generate_and_notify_emergency(
                user_id=user_id,
                user_name=user_name,
                emergency_context=emergency_context,
                caregivers=caregivers,
            )
        )
        print(f"[SenioCare] Emergency report + notification auto-triggered for {user_id}")

    except Exception as e:
        print(f"[SenioCare] Emergency report trigger failed: {e}")


async def _generate_and_notify_emergency(
    user_id: str,
    user_name: str,
    emergency_context: dict,
    caregivers: list[dict],
) -> None:
    """Generate an emergency report and notify caregivers.

    This runs as a background task via asyncio.create_task().
    """
    try:
        from seniocare.tools.reports import generate_report

        # Step 1: Generate the emergency report
        result = await generate_report(
            user_id=user_id,
            report_type="emergency",
            emergency_context=emergency_context,
        )
        report_id = result.get("report_id", "unknown")
        print(f"[SenioCare] Emergency report generated: {report_id}")

        # Step 2: Notify caregivers via FCM
        if caregivers:
            from app.notifications import notify_caregivers

            notif_result = await notify_caregivers(
                caregivers=caregivers,
                elder_name=user_name,
                report_type="emergency",
                report_id=report_id,
                report_summary="تم رصد حالة طوارئ أثناء المحادثة. اطلع على التقرير فوراً.",
                elder_user_id=user_id,
            )
            print(
                f"[SenioCare] 🔔 Emergency notifications: "
                f"{notif_result.get('sent', 0)} sent, "
                f"{notif_result.get('failed', 0)} failed"
            )
        else:
            print(f"[SenioCare] ⚠️ No caregivers registered for {user_id} — skipping notification")

    except Exception as e:
        print(f"[SenioCare] Emergency report/notification failed: {e}")
