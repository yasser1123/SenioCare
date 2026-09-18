"""User Preference tool - saves and retrieves user food/activity preferences.

Allows the agent to learn and remember user preferences expressed during
conversation (e.g., "I like meat", "I don't like fish"). Preferences are
stored in user:-scoped state, so they persist across all sessions.
"""

from google.adk.tools import ToolContext

from seniocare.tools._text import normalize_text

# Explicit pairing. The previous `key.replace("likes", "dislikes")` produced
# "food_disdislikes" for a dislike, so a like was never removed when the user
# changed their mind (AUDIT C-05).
OPPOSITE_KEY = {
    "food_likes": "food_dislikes", "food_dislikes": "food_likes",
    "exercise_likes": "exercise_dislikes", "exercise_dislikes": "exercise_likes",
    "general_likes": "general_dislikes", "general_dislikes": "general_likes",
}


def save_user_preference(
    preference_type: str,
    items: list,
    is_positive: bool,
    tool_context: ToolContext,
) -> dict:
    """
    Save a user preference expressed during conversation.

    Call this when the user expresses a food or activity preference,
    such as "I like meat", "I don't like fish", "I prefer walking".

    Args:
        preference_type: Type of preference — "food", "exercise", or "general".
        items: List of items the user likes or dislikes
               (e.g., ["meat", "chicken"] or ["fish", "seafood"]).
        is_positive: True if the user LIKES these items, False if they DISLIKE them.
        tool_context: The tool context for state access.

    Returns:
        dict: Confirmation of saved preferences.
    """
    state = tool_context.state

    # Get existing preferences or initialize empty
    preferences = state.get("user:preferences", {
        "food_likes": [],
        "food_dislikes": [],
        "exercise_likes": [],
        "exercise_dislikes": [],
        "general_likes": [],
        "general_dislikes": [],
    })

    # Determine the key based on type and polarity
    if preference_type == "food":
        key = "food_likes" if is_positive else "food_dislikes"
    elif preference_type == "exercise":
        key = "exercise_likes" if is_positive else "exercise_dislikes"
    else:
        key = "general_likes" if is_positive else "general_dislikes"

    # Add new items (normalised, de-duplicated, order preserved)
    new_items = [normalize_text(item) for item in items if str(item).strip()]
    new_items = list(dict.fromkeys(i for i in new_items if i))
    merged = list(dict.fromkeys([normalize_text(i) for i in preferences.get(key, [])] + new_items))
    preferences[key] = [i for i in merged if i]

    # The user changed their mind: drop the same items from the opposite list.
    opposite_key = OPPOSITE_KEY[key]
    preferences[opposite_key] = [
        item for item in preferences.get(opposite_key, [])
        if normalize_text(item) not in new_items
    ]

    # Save to user:-scoped state (persists across all sessions)
    state["user:preferences"] = preferences

    action = "يحب" if is_positive else "لا يحب"
    return {
        "status": "success",
        "message": f"تم حفظ تفضيل المستخدم: {action} {', '.join(new_items)}",
        "preference_type": preference_type,
        "items": new_items,
        "is_positive": is_positive,
        "current_preferences": preferences,
    }
