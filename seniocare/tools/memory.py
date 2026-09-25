"""Long-term memory: durable facts the user shares in conversation.

ADK 1.22 ships only an in-memory memory service (lost on restart) and Vertex
AI memory services (Google Cloud), and none was configured, so nothing said
in one conversation was available in the next (docs/ARCHITECTURE.md). Facts
are kept instead in user:-scoped state, which the DatabaseSessionService
persists in PostgreSQL (Neon) across all of the user's sessions, next to the
profile and preferences. seniocare/profile.py shows the newest facts to every
LLM stage; GET/DELETE /user-memory/{user_id} lets the user see and erase them.
"""

from datetime import datetime, timezone

from google.adk.tools import ToolContext

from seniocare.profile import KEY_MEMORY_FACTS
from seniocare.tools._text import normalize_text

MAX_FACTS = 50
CATEGORIES = ("family", "health_history", "routine", "likes", "social", "other")


def remember_fact(fact: str, category: str, tool_context: ToolContext) -> dict:
    """
    Remember a durable personal fact the user shared, for future conversations.

    Call this when the user tells you something about their life that will
    still matter next week: family ("my daughter Mona visits on Fridays"),
    health history ("I had knee surgery in 2020"), routine ("I walk after
    Maghrib"), what they enjoy ("I love Umm Kulthum"). Do NOT call it for
    passing feelings, for food/exercise likes (use save_user_preference), or
    for medications/conditions (those come from the app's health profile).

    Args:
        fact: One short sentence, in the user's language, stating the fact.
        category: One of "family", "health_history", "routine", "likes",
                  "social", "other".
        tool_context: The tool context for state access.

    Returns:
        dict: Confirmation with the number of remembered facts.
    """
    text = " ".join(str(fact or "").split())[:200]
    if not text:
        return {"status": "error", "message": "empty fact"}
    cat = category if category in CATEGORIES else "other"

    facts = list(tool_context.state.get(KEY_MEMORY_FACTS) or [])
    key = normalize_text(text)
    if any(normalize_text(f.get("fact", "")) == key for f in facts):
        return {"status": "success", "message": "already remembered", "count": len(facts)}

    facts.append({"fact": text, "category": cat, "date": datetime.now(timezone.utc).date().isoformat()})
    facts = facts[-MAX_FACTS:]
    tool_context.state[KEY_MEMORY_FACTS] = facts
    return {"status": "success", "message": f"تم حفظ المعلومة: {text}", "category": cat, "count": len(facts)}
