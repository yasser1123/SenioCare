"""Image analysis router — medication OCR and medical report vision analysis."""

from fastapi import APIRouter, HTTPException

from app.schemas.image import MedicationImageRequest, MedicalReportRequest

router = APIRouter(tags=["Image Analysis"])


@router.post("/analyze-medication-image")
async def analyze_medication_image_endpoint(request: MedicationImageRequest):
    """
    Analyze a medication box/package image using OCR AI.

    Extracts: medication name, active ingredient, dose/concentration.
    Returns extracted data directly — no database storage.
    Requires: `ollama pull richardyoung/olmocr2:7b-q8`
    """
    from seniocare.image_analysis.medication_analyzer import analyze_medication_image
    from seniocare.image_analysis.common import validate_base64_image

    if not validate_base64_image(request.image_base64):
        return {"success": False, "error": "Invalid base64 image data"}

    result = await analyze_medication_image(
        image_base64=request.image_base64,
        user_id=request.user_id,
    )
    return result.model_dump()


@router.post("/analyze-medical-report")
async def analyze_medical_report_endpoint(request: MedicalReportRequest):
    """
    Analyze a medical report image using vision AI.

    Two-pass analysis:
      1. Extract structured data (lab values, findings, report type)
      2. Evaluate health situation and classify severity

    Results are stored in the database for historical tracking.
    Requires: `ollama pull llama3.2-vision`
    """
    from seniocare.image_analysis.report_analyzer import analyze_medical_report
    from seniocare.image_analysis.common import validate_base64_image

    if not validate_base64_image(request.image_base64):
        return {"success": False, "error": "Invalid base64 image data"}

    result = await analyze_medical_report(
        image_base64=request.image_base64,
        user_id=request.user_id,
    )
    return result.model_dump()


@router.get("/user-medical-reports/{user_id}")
async def get_user_medical_reports(user_id: str):
    """
    Retrieve all previously analyzed medical reports for a user.

    Returns reports ordered by scan date (most recent first).
    """
    from seniocare.image_analysis.report_analyzer import get_user_reports

    reports = get_user_reports(user_id)
    return {
        "success": True,
        "user_id": user_id,
        "count":   len(reports),
        "reports": reports,
    }
