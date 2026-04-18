"""Pydantic schemas for user profile endpoints."""

from typing import List, Optional
from pydantic import BaseModel


class MedicationItem(BaseModel):
    """A single medication entry."""
    name: str
    dose: str


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
    caregiver_ids: List[str] = []


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
