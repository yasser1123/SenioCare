"""Chat history router — GET /chat-history/..."""

from fastapi import APIRouter, HTTPException

from app.config import session_service

router = APIRouter(tags=["Chat History"])


@router.get("/chat-history/{user_id}")
async def get_chat_history(user_id: str):
    """
    List all conversations for a user with headlines and previews.

    Returns a lightweight list of sessions — no full event logs loaded.
    Headlines and previews are stored in session state on the first turn,
    so this endpoint only reads state metadata.
    """
    try:
        response = await session_service.list_sessions(
            app_name="seniocare",
            user_id=user_id,
        )

        conversations = []
        for session in response.sessions:
            # Skip internal profile-setup sessions
            if session.id.startswith("_profile_"):
                continue

            conversations.append({
                "session_id":  session.id,
                "headline":    session.state.get("session_headline", "💬 محادثة جديدة"),
                "preview":     session.state.get("session_preview", ""),
                "turn_count":  session.state.get("conversation_turn_count", 0),
            })

        return {
            "success":       True,
            "user_id":       user_id,
            "count":         len(conversations),
            "conversations": conversations,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get chat history: {e}")


@router.get("/chat-history/{user_id}/{session_id}")
async def get_conversation_turns(user_id: str, session_id: str):
    """
    Get the full conversation turns for a specific session.

    Loads the session's event log and returns each user/agent exchange
    as a structured turn object.
    """
    try:
        session = await session_service.get_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=session_id,
        )

        if session is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        turns = []
        for event in session.events:
            if not hasattr(event, "content") or not event.content:
                continue
            if not event.content.parts:
                continue

            text = event.content.parts[0].text or ""
            if not text.strip():
                continue

            # Only include user messages and final formatter output
            if event.author == "user":
                turns.append({
                    "role":      "user",
                    "text":      text,
                    "timestamp": str(event.timestamp) if hasattr(event, "timestamp") else None,
                })
            elif event.author == "formatter_agent":
                turns.append({
                    "role":      "agent",
                    "text":      text,
                    "timestamp": str(event.timestamp) if hasattr(event, "timestamp") else None,
                })

        return {
            "success":     True,
            "session_id":  session_id,
            "headline":    session.state.get("session_headline", "💬 محادثة جديدة"),
            "turn_count":  len([t for t in turns if t["role"] == "user"]),
            "turns":       turns,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get conversation: {e}")
