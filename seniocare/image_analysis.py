"""
Image Analysis Module for SenioCare
====================================

This module provides image analysis capabilities for:
1. Medical Reports - Extract information from lab results, prescriptions, etc.
2. Medication Images - Extract medication name and active ingredients

Uses llama3.2-vision via Ollama for image understanding.
When llama3.2-vision is not available, returns a placeholder response.
"""

import base64
import json
import httpx
from typing import Optional
from pydantic import BaseModel
from enum import Enum


class ImageType(str, Enum):
    """Types of images that can be analyzed."""
    MEDICAL_REPORT = "medical_report"
    MEDICATION = "medication"


class MedicationInfo(BaseModel):
    """Extracted medication information."""
    medication_name: str
    active_ingredient: Optional[str] = None
    dosage: Optional[str] = None
    manufacturer: Optional[str] = None
    expiry_date: Optional[str] = None


class MedicalReportInfo(BaseModel):
    """Extracted medical report information."""
    report_type: str  # e.g., "blood_test", "x_ray", "prescription"
    date: Optional[str] = None
    key_findings: list[str] = []
    values: dict = {}  # e.g., {"blood_sugar": "120 mg/dL", "cholesterol": "180 mg/dL"}
    recommendations: list[str] = []


class ImageAnalysisResult(BaseModel):
    """Result of image analysis."""
    success: bool
    image_type: ImageType
    medication_info: Optional[MedicationInfo] = None
    report_info: Optional[MedicalReportInfo] = None
    raw_analysis: Optional[str] = None
    error: Optional[str] = None


# Ollama API configuration
OLLAMA_BASE_URL = "http://localhost:11434"
VISION_MODEL = "llama3.2-vision"  # Will be pulled later


async def check_vision_model_available() -> bool:
    """Check if the vision model is available in Ollama."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
            if response.status_code == 200:
                models = response.json().get("models", [])
                for model in models:
                    if VISION_MODEL in model.get("name", ""):
                        return True
            return False
    except Exception:
        return False


async def analyze_image_with_ollama(
    image_base64: str,
    image_type: ImageType,
    prompt: str
) -> str:
    """
    Send image to Ollama vision model for analysis.
    
    Args:
        image_base64: Base64 encoded image
        image_type: Type of image being analyzed
        prompt: Analysis instructions
        
    Returns:
        Raw text response from the model
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        payload = {
            "model": VISION_MODEL,
            "prompt": prompt,
            "images": [image_base64],
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for accurate extraction
            }
        }
        
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload
        )
        
        if response.status_code == 200:
            return response.json().get("response", "")
        else:
            raise Exception(f"Ollama API error: {response.status_code} - {response.text}")


def get_medication_prompt() -> str:
    """Prompt for medication image analysis."""
    return """Analyze this medication/medicine image and extract the following information in JSON format:

{
    "medication_name": "exact name of the medication",
    "active_ingredient": "main active ingredient(s)",
    "dosage": "dosage strength (e.g., 500mg)",
    "manufacturer": "manufacturer name if visible",
    "expiry_date": "expiry date if visible"
}

Be precise and only include information that is clearly visible in the image.
If any field is not visible, set it to null.
Respond ONLY with the JSON, no other text."""


def get_medical_report_prompt() -> str:
    """Prompt for medical report image analysis."""
    return """Analyze this medical report/lab result image and extract the following information in JSON format:

{
    "report_type": "type of report (blood_test, x_ray, prescription, etc.)",
    "date": "date of the report if visible",
    "key_findings": ["list of important findings or abnormal values"],
    "values": {"test_name": "value with unit", ...},
    "recommendations": ["any recommendations mentioned"]
}

Focus on:
- Blood sugar levels (fasting, HbA1c)
- Blood pressure readings
- Cholesterol (total, HDL, LDL)
- Kidney function (creatinine, BUN)
- Liver function (ALT, AST)
- Any flagged abnormal values

Be precise and only include information that is clearly visible.
Respond ONLY with the JSON, no other text."""


def parse_medication_response(response: str) -> MedicationInfo:
    """Parse the model response into MedicationInfo."""
    try:
        # Try to extract JSON from response
        response = response.strip()
        if response.startswith("```"):
            # Remove markdown code blocks
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        
        data = json.loads(response)
        return MedicationInfo(
            medication_name=data.get("medication_name", "Unknown"),
            active_ingredient=data.get("active_ingredient"),
            dosage=data.get("dosage"),
            manufacturer=data.get("manufacturer"),
            expiry_date=data.get("expiry_date")
        )
    except (json.JSONDecodeError, KeyError) as e:
        return MedicationInfo(
            medication_name="Could not parse",
            active_ingredient=None
        )


def parse_report_response(response: str) -> MedicalReportInfo:
    """Parse the model response into MedicalReportInfo."""
    try:
        # Try to extract JSON from response
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        
        data = json.loads(response)
        return MedicalReportInfo(
            report_type=data.get("report_type", "unknown"),
            date=data.get("date"),
            key_findings=data.get("key_findings", []),
            values=data.get("values", {}),
            recommendations=data.get("recommendations", [])
        )
    except (json.JSONDecodeError, KeyError) as e:
        return MedicalReportInfo(
            report_type="Could not parse",
            key_findings=[]
        )


async def analyze_image(
    image_base64: str,
    image_type: ImageType,
    user_id: str,
    session_id: str
) -> ImageAnalysisResult:
    """
    Main function to analyze an image.
    
    Args:
        image_base64: Base64 encoded image data
        image_type: Type of image (medication or medical_report)
        user_id: User identifier
        session_id: Session identifier
        
    Returns:
        ImageAnalysisResult with extracted information
    """
    # Check if vision model is available
    model_available = await check_vision_model_available()
    
    if not model_available:
        return ImageAnalysisResult(
            success=False,
            image_type=image_type,
            error=f"Vision model '{VISION_MODEL}' not available. Please run: ollama pull {VISION_MODEL}"
        )
    
    try:
        # Get appropriate prompt based on image type
        if image_type == ImageType.MEDICATION:
            prompt = get_medication_prompt()
        else:
            prompt = get_medical_report_prompt()
        
        # Analyze with Ollama
        raw_response = await analyze_image_with_ollama(image_base64, image_type, prompt)
        
        # Parse response based on image type
        if image_type == ImageType.MEDICATION:
            medication_info = parse_medication_response(raw_response)
            return ImageAnalysisResult(
                success=True,
                image_type=image_type,
                medication_info=medication_info,
                raw_analysis=raw_response
            )
        else:
            report_info = parse_report_response(raw_response)
            return ImageAnalysisResult(
                success=True,
                image_type=image_type,
                report_info=report_info,
                raw_analysis=raw_response
            )
            
    except Exception as e:
        return ImageAnalysisResult(
            success=False,
            image_type=image_type,
            error=str(e)
        )


# Utility function to validate base64 image
def validate_base64_image(image_base64: str) -> bool:
    """Check if the provided string is valid base64 image data."""
    try:
        # Remove data URL prefix if present
        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]
        
        # Try to decode
        decoded = base64.b64decode(image_base64, validate=True)
        return len(decoded) > 0
    except Exception:
        return False
