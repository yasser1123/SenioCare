"""
Image Analysis Package for SenioCare
=====================================

Two separate analyzer models:
1. MedicationAnalyzer - Uses olmocr2 to extract medicine name, active ingredient, concentration
2. ReportAnalyzer - Uses llama3.2-vision to extract and summarize medical reports
"""

from seniocare.image_analysis.medication_analyzer import analyze_medication_image, MedicationScanResult
from seniocare.image_analysis.report_analyzer import analyze_medical_report, ReportAnalysisResult
from seniocare.image_analysis.common import validate_base64_image

__all__ = [
    "analyze_medication_image",
    "analyze_medical_report",
    "validate_base64_image",
    "MedicationScanResult",
    "ReportAnalysisResult",
]
