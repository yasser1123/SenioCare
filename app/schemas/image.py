"""Pydantic schemas for image analysis endpoints."""

from pydantic import BaseModel


class MedicationImageRequest(BaseModel):
    """Request model for medication image analysis."""
    user_id: str
    image_base64: str  # Base64-encoded image of a medication box


class MedicalReportRequest(BaseModel):
    """Request model for medical report image analysis."""
    user_id: str
    image_base64: str  # Base64-encoded image of a medical report
