"""
Shared utilities for the image analysis package.

Common Ollama API interaction, base64 validation, and JSON parsing
used by both the medication and report analyzers.
"""

import base64
import json
import httpx
from typing import Optional


# ---------------------------------------------------------------------------
# Ollama API configuration
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = "http://localhost:11434"


async def check_model_available(model_name: str) -> bool:
    """Check if a specific model is available in Ollama."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
            if response.status_code == 200:
                models = response.json().get("models", [])
                for model in models:
                    if model_name in model.get("name", ""):
                        return True
            return False
    except Exception:
        return False


async def call_ollama_vision(
    model_name: str,
    image_base64: str,
    prompt: str,
    temperature: float = 0.1,
    timeout: float = 120.0,
) -> str:
    """
    Send an image to an Ollama vision model for analysis.

    Args:
        model_name: The Ollama model to use (e.g. 'llama3.2-vision', 'richardyoung/olmocr2:7b-q8')
        image_base64: Base64 encoded image
        prompt: Analysis instructions
        temperature: Sampling temperature (lower = more deterministic)
        timeout: Request timeout in seconds

    Returns:
        Raw text response from the model
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        payload = {
            "model": model_name,
            "prompt": prompt,
            "images": [image_base64],
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
        )

        if response.status_code == 200:
            return response.json().get("response", "")
        else:
            raise Exception(
                f"Ollama API error: {response.status_code} - {response.text}"
            )


def parse_json_from_response(response: str) -> dict:
    """
    Extract and parse JSON from a model response.

    Handles responses wrapped in markdown code fences like:
        ```json
        { ... }
        ```

    Args:
        response: Raw text response from the model

    Returns:
        Parsed dictionary from the JSON content

    Raises:
        json.JSONDecodeError: If no valid JSON can be extracted
    """
    response = response.strip()

    # Strip markdown code fences
    if response.startswith("```"):
        parts = response.split("```")
        if len(parts) >= 2:
            response = parts[1]
            if response.startswith("json"):
                response = response[4:]
        response = response.strip()

    # Try to find JSON object in the response
    start = response.find("{")
    end = response.rfind("}") + 1
    if start != -1 and end > start:
        response = response[start:end]

    return json.loads(response)


def validate_base64_image(image_base64: str) -> bool:
    """Check if the provided string is valid base64 image data."""
    try:
        # Remove data URL prefix if present
        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]

        decoded = base64.b64decode(image_base64, validate=True)
        return len(decoded) > 0
    except Exception:
        return False


def strip_base64_prefix(image_base64: str) -> str:
    """Remove data URL prefix (e.g. 'data:image/png;base64,') if present."""
    if "," in image_base64:
        return image_base64.split(",", 1)[1]
    return image_base64
