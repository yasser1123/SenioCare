"""
Shared LLM model configuration for all SenioCare agents.

Centralizes the Ollama model setup so all agents use the same
model and base URL. When OLLAMA_BASE_URL is set (e.g. Colab ngrok),
LiteLLM routes inference to the remote server.

Usage:
    from seniocare.model import get_model
    agent = LlmAgent(model=get_model(), ...)
"""

from google.adk.models.lite_llm import LiteLlm


def get_model() -> LiteLlm:
    """Create a LiteLlm instance with the configured Ollama endpoint.

    Reads OLLAMA_BASE_URL and OLLAMA_MODEL from app.config.
    If OLLAMA_BASE_URL is set, LiteLLM routes to that remote server.
    If not set, LiteLLM defaults to http://localhost:11434.

    Returns:
        Configured LiteLlm instance.
    """
    from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL

    if OLLAMA_BASE_URL:
        return LiteLlm(model=OLLAMA_MODEL, api_base=OLLAMA_BASE_URL)
    else:
        return LiteLlm(model=OLLAMA_MODEL)
