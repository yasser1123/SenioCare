"""User Preference tool - saves and retrieves user food/activity preferences.

Allows the agent to learn and remember user preferences expressed during
conversation (e.g., "I like meat", "I don't like fish"). Preferences are
stored in user:-scoped state, so they persist across all sessions.
"""

from google.adk.tools import ToolContext


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

    # Add new items (avoid duplicates)
    existing = set(preferences.get(key, []))
    new_items = [item.lower().strip() for item in items]
    existing.update(new_items)
    preferences[key] = list(existing)

    # If user now likes something they previously disliked (or vice versa), remove conflict
    opposite_key = key.replace("likes", "dislikes") if "likes" in key else key.replace("dislikes", "likes")
    if opposite_key in preferences:
        preferences[opposite_key] = [
            item for item in preferences[opposite_key]
            if item not in new_items
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
