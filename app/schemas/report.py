"""Pydantic schemas for health report endpoints."""

from typing import Optional
from pydantic import BaseModel


class GenerateReportRequest(BaseModel):
    """Request model for report generation.

    Only user_id and report_type are required. All other data
    (user profile, session history, medical reports) is automatically
    fetched from the user's session state and database.
    """
    user_id: str
    report_type: str  # 'daily', 'weekly', 'monthly', 'emergency'
    start_date: Optional[str] = None  # Override start date (YYYY-MM-DD)
    end_date: Optional[str] = None    # Override end date (YYYY-MM-DD)
    # Send FCM push notification to caregivers after generation
    notify_caregiver: bool = False
