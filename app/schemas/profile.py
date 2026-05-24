"""Pydantic schemas for user profile endpoints."""

from typing import List, Optional
from pydantic import BaseModel


class MedicationItem(BaseModel):
    """A single medication entry."""
    name: str
    dose: str


class CaregiverInfo(BaseModel):
    """Caregiver contact info for push notifications.

    Sent by the caregiver's Flutter app via POST /register-caregiver-fcm.
    Stored in the elder's ADK session state under user:caregivers.
    """
    caregiver_id: str                          # MongoDB Caregiver._id
    name: Optional[str] = None                 # Caregiver's display name
    relationship: Optional[str] = None         # son | daughter | nurse | other
    fcm_token: Optional[str] = None            # Firebase Cloud Messaging device token


class CaregiverFCMRequest(BaseModel):
    """Request model for caregiver FCM token registration.

    Called by the caregiver's Flutter app after sign-in to register
    their device for push notifications about their elder.
    """
    elder_user_id: str                         # The elder's user_id in the AI backend
    caregiver_id: str                          # The caregiver's own document ID
    name: Optional[str] = None                 # Caregiver's display name
    relationship: Optional[str] = None         # son | daughter | nurse | other
    fcm_token: str                             # Firebase Cloud Messaging device token


class UserProfileRequest(BaseModel):
    """
    Full user health profile.
    Aligned with the backend ElderCreate schema.
    """
    user_name: Optional[str] = None           # Display name
    age: Optional[int] = None
    weight: Optional[float] = None            # kg
    height: Optional[float] = None            # cm
    gender: Optional[str] = None              # "male" / "female"
    chronicDiseases: List[str] = []
    allergies: List[str] = []
    medications: List[MedicationItem] = []
    mobilityStatus: Optional[str] = "limited"
    bloodType: Optional[str] = None           # e.g. "A+", "O-"
    caregiver_ids: List[str] = []             # Backward compat: plain IDs
    caregivers: List[CaregiverInfo] = []      # Rich caregiver data with FCM tokens


class PartialProfileUpdate(BaseModel):
    """Partial profile update — only include fields that changed."""
    user_name: Optional[str] = None
    age: Optional[int] = None
    weight: Optional[float] = None
    height: Optional[float] = None
    gender: Optional[str] = None
    chronicDiseases: Optional[List[str]] = None
    allergies: Optional[List[str]] = None
    medications: Optional[List[MedicationItem]] = None
    mobilityStatus: Optional[str] = None
    bloodType: Optional[str] = None
    caregiver_ids: Optional[List[str]] = None
    caregivers: Optional[List[CaregiverInfo]] = None
