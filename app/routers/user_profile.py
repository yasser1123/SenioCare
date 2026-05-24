"""User profile router — push/pull user health data via ADK user-scoped state."""

import uuid

from fastapi import APIRouter, HTTPException

from app.config import session_service
from app.schemas.profile import (
    UserProfileRequest,
    PartialProfileUpdate,
    CaregiverFCMRequest,
)

router = APIRouter(tags=["User Profile"])

# State keys that map to profile fields
_PROFILE_STATE_KEYS = [
    "user:user_id", "user:user_name", "user:age",
    "user:weight", "user:height", "user:gender",
    "user:chronicDiseases", "user:allergies", "user:medications",
    "user:mobilityStatus", "user:bloodType", "user:caregiver_ids",
    "user:caregivers",
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
                "user:caregivers":      [c.model_dump() for c in profile.caregivers],
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
            "caregivers":      session.state.get("user:caregivers"),
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
        if updates.caregivers      is not None: state_updates["user:caregivers"]      = [c.model_dump() for c in updates.caregivers]
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


# =========================================================================
# CAREGIVER FCM REGISTRATION
# =========================================================================


@router.post("/register-caregiver-fcm")
async def register_caregiver_fcm(request: CaregiverFCMRequest):
    """Register a caregiver's FCM token for push notifications about an elder.

    Called by the caregiver's Flutter app after sign-in.
    The caregiver provides:
      - elder_user_id: which elder to receive notifications about
      - caregiver_id: their own caregiver document ID
      - name: their display name
      - relationship: their relationship to the elder
      - fcm_token: their device's Firebase Cloud Messaging token

    The caregiver's info is stored in the elder's ADK session state under
    user:caregivers as a list. If this caregiver already exists in the list,
    their data (especially fcm_token) is updated. Otherwise they are appended.
    """
    try:
        elder_user_id = request.elder_user_id

        # Read the elder's current session state
        temp_session_id = f"_fcm_reg_{uuid.uuid4().hex[:8]}"
        session = await session_service.create_session(
            app_name="seniocare",
            user_id=elder_user_id,
            session_id=temp_session_id,
        )

        # Get current caregivers list (or empty if none registered yet)
        caregivers = session.state.get("user:caregivers", []) or []

        # Build the new caregiver entry
        new_caregiver = {
            "caregiver_id": request.caregiver_id,
            "name": request.name,
            "relationship": request.relationship,
            "fcm_token": request.fcm_token,
        }

        # Check if this caregiver already exists — update if so, append if not
        updated = False
        for i, cg in enumerate(caregivers):
            if cg.get("caregiver_id") == request.caregiver_id:
                caregivers[i] = new_caregiver
                updated = True
                break

        if not updated:
            caregivers.append(new_caregiver)

        # Clean up the read session
        await session_service.delete_session(
            app_name="seniocare",
            user_id=elder_user_id,
            session_id=temp_session_id,
        )

        # Write the updated caregivers list back to the elder's state
        write_session_id = f"_fcm_write_{uuid.uuid4().hex[:8]}"
        await session_service.create_session(
            app_name="seniocare",
            user_id=elder_user_id,
            session_id=write_session_id,
            state={"user:caregivers": caregivers},
        )
        await session_service.delete_session(
            app_name="seniocare",
            user_id=elder_user_id,
            session_id=write_session_id,
        )

        action = "updated" if updated else "registered"
        print(
            f"[FCM] Caregiver {request.name} ({request.relationship}) "
            f"{action} for elder {elder_user_id}"
        )

        return {
            "success": True,
            "message": f"Caregiver {action} successfully",
            "elder_user_id": elder_user_id,
            "caregiver_id": request.caregiver_id,
            "action": action,
            "total_caregivers": len(caregivers),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to register caregiver FCM: {e}",
        )
