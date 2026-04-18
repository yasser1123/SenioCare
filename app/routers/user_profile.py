"""User profile router — push/pull user health data via ADK user-scoped state."""

import uuid

from fastapi import APIRouter, HTTPException

from app.config import session_service
from app.schemas.profile import UserProfileRequest, PartialProfileUpdate

router = APIRouter(tags=["User Profile"])

# State keys that map to profile fields
_PROFILE_STATE_KEYS = [
    "user:user_id", "user:user_name", "user:age",
    "user:weight", "user:height", "user:gender",
    "user:chronicDiseases", "user:allergies", "user:medications",
    "user:mobilityStatus", "user:bloodType", "user:caregiver_ids",
]


@router.post("/set-user-profile/{user_id}")
async def set_user_profile(user_id: str, profile: UserProfileRequest):
    """
    Push a user health profile to persist across all sessions.

    Call this once after registration, and again whenever the profile changes.
    Data is stored with user: prefix in ADK session state, making it
    automatically available in ALL future sessions for this user_id.
    """
    try:
        temp_session_id = f"_profile_setup_{uuid.uuid4().hex[:8]}"

        await session_service.create_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=temp_session_id,
            state={
                "user:user_id":         user_id,
                "user:user_name":       profile.user_name,
                "user:age":             profile.age,
                "user:weight":          profile.weight,
                "user:height":          profile.height,
                "user:gender":          profile.gender,
                "user:chronicDiseases": profile.chronicDiseases,
                "user:allergies":       profile.allergies,
                "user:medications":     [m.model_dump() for m in profile.medications],
                "user:mobilityStatus":  profile.mobilityStatus,
                "user:bloodType":       profile.bloodType,
                "user:caregiver_ids":   profile.caregiver_ids,
            }
        )

        # Clean up temp session — the user:-scoped state persists independently
        await session_service.delete_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=temp_session_id,
        )

        return {
            "success":      True,
            "message":      f"Profile saved for user {user_id}",
            "user_id":      user_id,
            "profile_keys": _PROFILE_STATE_KEYS,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save profile: {e}")


@router.get("/get-user-profile/{user_id}")
async def get_user_profile(user_id: str):
    """
    Retrieve the user health profile stored in ADK session state.

    Returns the user:-prefixed keys set via /set-user-profile or
    populated by the agent's before_agent_callback.
    """
    try:
        temp_session_id = f"_profile_read_{uuid.uuid4().hex[:8]}"
        session = await session_service.create_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=temp_session_id,
        )

        profile = {
            "user_id":         session.state.get("user:user_id"),
            "user_name":       session.state.get("user:user_name"),
            "age":             session.state.get("user:age"),
            "weight":          session.state.get("user:weight"),
            "height":          session.state.get("user:height"),
            "gender":          session.state.get("user:gender"),
            "chronicDiseases": session.state.get("user:chronicDiseases"),
            "allergies":       session.state.get("user:allergies"),
            "medications":     session.state.get("user:medications"),
            "mobilityStatus":  session.state.get("user:mobilityStatus"),
            "bloodType":       session.state.get("user:bloodType"),
            "caregiver_ids":   session.state.get("user:caregiver_ids"),
            "preferences":     session.state.get("user:preferences"),
        }

        await session_service.delete_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=temp_session_id,
        )

        if profile["user_id"] is None:
            return {
                "success": False,
                "message": f"No profile found for user {user_id}. Call /set-user-profile first.",
                "profile": None,
            }

        return {"success": True, "user_id": user_id, "profile": profile}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get profile: {e}")


@router.post("/sync-user-profile/{user_id}")
async def sync_user_profile(user_id: str, updates: PartialProfileUpdate):
    """
    Partially update user profile data (only the fields that changed).

    Call this when the backend detects changes — e.g. doctor changed a
    medication, a new allergy was recorded. Only send modified fields.
    """
    try:
        state_updates: dict = {}

        if updates.user_name       is not None: state_updates["user:user_name"]       = updates.user_name
        if updates.age             is not None: state_updates["user:age"]             = updates.age
        if updates.weight          is not None: state_updates["user:weight"]          = updates.weight
        if updates.height          is not None: state_updates["user:height"]          = updates.height
        if updates.gender          is not None: state_updates["user:gender"]          = updates.gender
        if updates.chronicDiseases is not None: state_updates["user:chronicDiseases"] = updates.chronicDiseases
        if updates.allergies       is not None: state_updates["user:allergies"]       = updates.allergies
        if updates.mobilityStatus  is not None: state_updates["user:mobilityStatus"]  = updates.mobilityStatus
        if updates.bloodType       is not None: state_updates["user:bloodType"]       = updates.bloodType
        if updates.caregiver_ids   is not None: state_updates["user:caregiver_ids"]   = updates.caregiver_ids
        if updates.medications     is not None:
            state_updates["user:medications"] = [m.model_dump() for m in updates.medications]

        if not state_updates:
            return {"success": False, "message": "No fields provided for update"}

        temp_session_id = f"_profile_sync_{uuid.uuid4().hex[:8]}"
        await session_service.create_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=temp_session_id,
            state=state_updates,
        )
        await session_service.delete_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=temp_session_id,
        )

        return {
            "success":        True,
            "message":        f"Profile synced for user {user_id}",
            "updated_fields": list(state_updates.keys()),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync profile: {e}")
