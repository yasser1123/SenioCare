"""
Model configuration — one factory for every agent, any provider.
================================================================

All four agents call ``get_model()``. Which model answers, and where it runs,
is decided entirely by environment variables, so the same backend talks to a
local Ollama, a GPU on Colab behind a tunnel, or a hosted API without any
code change. Tools, prompts, sessions and the database never move: the model
only ever receives tool *schemas* and returns tool-call requests that ADK
executes in this process.

Environment variables (see .env.example):

    MODEL_NAME          LiteLLM model string, e.g.
                          ollama_chat/gemma4:e4b            local Ollama
                          openai/gemma4:e4b                 Colab Ollama, OpenAI-compatible /v1
                          hosted_vllm/google/gemma-3-4b-it  Colab vLLM
                          gemini/gemini-2.5-flash           Google AI Studio
                          openai/llama-3.3-70b-versatile    Groq / OpenRouter / any OpenAI-compatible
    MODEL_API_BASE      Base URL for self-hosted or OpenAI-compatible endpoints.
                        For ollama_chat/ this is the Ollama root (http://host:11434);
                        for openai/ and hosted_vllm/ it includes /v1.
    MODEL_API_KEY       API key. Optional for local/self-hosted endpoints.
    MODEL_TIMEOUT_S     Per-request timeout passed to LiteLLM (default 120).
    MODEL_TEMPERATURE   Sampling temperature. Unset = provider default.
    MODEL_MAX_TOKENS    Completion cap. Unset = provider default.
    MODEL_EXTRA_JSON    JSON object of additional litellm.completion kwargs
                        (escape hatch, e.g. {"top_p": 0.9, "num_ctx": 8192}).

``OLLAMA_MODEL`` / ``OLLAMA_BASE_URL`` are still honoured as fallbacks for
the older configuration.
"""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from google.adk.models.lite_llm import LiteLlm

load_dotenv()

DEFAULT_MODEL = "ollama_chat/gemma4:e4b"

# Providers whose OpenAI-compatible client refuses to start without *some*
# api_key even when the server does not check it (vLLM, Ollama /v1, llama.cpp).
_PLACEHOLDER_KEY_PREFIXES = ("openai/", "hosted_vllm/")
_PLACEHOLDER_KEY = "not-needed"


def _env(name: str, *fallbacks: str, default: str | None = None) -> str | None:
    for key in (name, *fallbacks):
        value = os.environ.get(key, "")
        if value.strip():
            return value.strip()
    return default


def _float_env(name: str) -> float | None:
    raw = _env(name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError as e:
        raise ValueError(f"{name} must be a number, got {raw!r}") from e


def _int_env(name: str) -> int | None:
    raw = _env(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as e:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from e


def model_settings() -> dict[str, Any]:
    """Resolve the model configuration from the environment.

    Returns the kwargs that ``LiteLlm`` (and therefore ``litellm.completion``)
    will receive, plus ``model``. Pure function of the environment; safe to
    call from the health check and the startup banner.
    """
    model = _env("MODEL_NAME", "OLLAMA_MODEL", default=DEFAULT_MODEL)
    api_base = _env("MODEL_API_BASE", "OLLAMA_BASE_URL")
    api_key = _env("MODEL_API_KEY")

    settings: dict[str, Any] = {"model": model}
    if api_base:
        settings["api_base"] = api_base.rstrip("/")
    if api_key:
        settings["api_key"] = api_key
    elif api_base and model.startswith(_PLACEHOLDER_KEY_PREFIXES):
        settings["api_key"] = _PLACEHOLDER_KEY

    timeout = _float_env("MODEL_TIMEOUT_S")
    settings["timeout"] = timeout if timeout is not None else 120.0

    temperature = _float_env("MODEL_TEMPERATURE")
    if temperature is not None:
        settings["temperature"] = temperature

    max_tokens = _int_env("MODEL_MAX_TOKENS")
    if max_tokens is not None:
        settings["max_tokens"] = max_tokens

    extra = _env("MODEL_EXTRA_JSON")
    if extra:
        try:
            parsed = json.loads(extra)
        except json.JSONDecodeError as e:
            raise ValueError(f"MODEL_EXTRA_JSON is not valid JSON: {e}") from e
        if not isinstance(parsed, dict):
            raise ValueError("MODEL_EXTRA_JSON must be a JSON object")
        settings.update(parsed)

    return settings


def get_model() -> LiteLlm:
    """Build the ``LiteLlm`` instance every agent uses.

    ``LiteLlm.__init__(model, **kwargs)`` forwards every kwarg to
    ``litellm.completion`` (google/adk/models/lite_llm.py, ``_additional_args``),
    which is how ``api_base``, ``api_key``, ``timeout`` and the sampling
    parameters reach the provider.
    """
    return LiteLlm(**model_settings())


def describe_model(mask_key: bool = True) -> dict[str, Any]:
    """Human-readable view of the active configuration for logs and /health."""
    settings = model_settings()
    model = settings["model"]
    provider = model.split("/", 1)[0] if "/" in model else "openai"
    api_base = settings.get("api_base")
    if api_base:
        location = "remote" if not any(h in api_base for h in ("localhost", "127.0.0.1")) else "local"
    elif provider in ("ollama", "ollama_chat"):
        location = "local"
    else:
        location = "provider-hosted"

    view = {
        "model": model,
        "provider": provider,
        "location": location,
        "api_base": api_base or _default_base_for(provider),
        "api_key": (
            ("set" if settings.get("api_key") not in (None, _PLACEHOLDER_KEY) else "none")
            if mask_key
            else settings.get("api_key")
        ),
        "timeout_s": settings.get("timeout"),
    }
    for key in ("temperature", "max_tokens"):
        if key in settings:
            view[key] = settings[key]
    return view


def _default_base_for(provider: str) -> str | None:
    if provider in ("ollama", "ollama_chat"):
        return "http://localhost:11434"
    return None


def probe_url() -> str | None:
    """A cheap GET that answers "is the model server reachable?".

    Returns None for provider-hosted APIs (Gemini, OpenAI, Groq…) where a
    reachability check is meaningless without an authenticated call.
    """
    view = describe_model()
    base = view["api_base"]
    if not base:
        return None
    if view["provider"] in ("ollama", "ollama_chat"):
        return f"{base}/api/tags"
    # OpenAI-compatible servers (Ollama /v1, vLLM, llama.cpp, LM Studio, …)
    return f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
