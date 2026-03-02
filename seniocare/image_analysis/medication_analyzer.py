"""
Medication Image Analyzer
=========================

Uses the richardyoung/olmocr2:7b-q8 model to extract medication information
from images of medication boxes / packages.

Extracts:
- Medication name
- Active ingredient
- Dose / concentration

Returns the extracted data directly to the backend — no database storage.
"""

import json
from typing import Optional
from pydantic import BaseModel

from seniocare.image_analysis.common import (
    check_model_available,
    call_ollama_vision,
    parse_json_from_response,
    validate_base64_image,
    strip_base64_prefix,
)


# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
MEDICATION_MODEL = "richardyoung/olmocr2:7b-q8"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
class MedicationScanResult(BaseModel):
    """Result of medication image analysis — returned directly to backend."""
    success: bool
    medication_name: Optional[str] = None
    active_ingredient: Optional[str] = None
    dosage: Optional[str] = None           # dose / concentration (e.g. "500mg", "10mg/5ml")
    manufacturer: Optional[str] = None
    expiry_date: Optional[str] = None
    raw_response: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
def _get_medication_prompt() -> str:
    """Prompt optimized for extracting medication info from box images."""
    return """You are a pharmaceutical OCR specialist. Analyze this image of a medication box or package.

Extract the following information and return it as a JSON object:

{
    "medication_name": "exact brand or generic name of the medication",
    "active_ingredient": "the active pharmaceutical ingredient(s)",
    "dosage": "dose strength or concentration (e.g. 500mg, 10mg/5ml, 200mg/tablet)",
    "manufacturer": "manufacturer or pharmaceutical company name if visible",
    "expiry_date": "expiry date if visible (format: MM/YYYY or as shown)"
}

IMPORTANT RULES:
- Read ALL visible text on the box carefully
- The medication name is usually the LARGEST text on the package
- The active ingredient is often listed below the brand name or on the side
- The dosage/concentration is typically near the medication name
- Only include information you can clearly read — set null for anything not visible
- Respond ONLY with the JSON object, no other text"""


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------
def _parse_medication_response(raw_response: str) -> MedicationScanResult:
    """Parse the model response into a MedicationScanResult."""
    try:
        data = parse_json_from_response(raw_response)
        return MedicationScanResult(
            success=True,
            medication_name=data.get("medication_name"),
            active_ingredient=data.get("active_ingredient"),
            dosage=data.get("dosage"),
            manufacturer=data.get("manufacturer"),
            expiry_date=data.get("expiry_date"),
            raw_response=raw_response,
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return MedicationScanResult(
            success=True,
            medication_name=None,
            active_ingredient=None,
            raw_response=raw_response,
            error="Could not parse structured data from model response",
        )


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------
async def analyze_medication_image(
    image_base64: str,
    user_id: str,
) -> MedicationScanResult:
    """
    Analyze a medication box image and extract name, active ingredient, dose.

    Uses richardyoung/olmocr2:7b-q8 for OCR-based extraction.
    Returns the result directly — no database storage.

    Args:
        image_base64: Base64 encoded image of the medication box
        user_id: User identifier (for logging/tracking)

    Returns:
        MedicationScanResult with extracted medication information
    """
    # Validate image
    if not validate_base64_image(image_base64):
        return MedicationScanResult(
            success=False,
            error="Invalid base64 image data",
        )

    # Check model availability
    model_available = await check_model_available(MEDICATION_MODEL)
    if not model_available:
        return MedicationScanResult(
            success=False,
            error=(
                f"Model '{MEDICATION_MODEL}' not available. "
                f"Please run: ollama pull {MEDICATION_MODEL}"
            ),
        )

    try:
        # Clean the base64 string
        clean_b64 = strip_base64_prefix(image_base64)

        # Call the OCR model
        raw_response = await call_ollama_vision(
            model_name=MEDICATION_MODEL,
            image_base64=clean_b64,
            prompt=_get_medication_prompt(),
            temperature=0.1,
        )

        # Parse and return
        result = _parse_medication_response(raw_response)
        return result

    except Exception as e:
        return MedicationScanResult(
            success=False,
            error=str(e),
        )
