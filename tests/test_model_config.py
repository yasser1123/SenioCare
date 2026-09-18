"""Tests for seniocare.model — the provider-agnostic model factory.

No database, no network: these only exercise environment → settings mapping.
"""

import importlib
import json

import pytest


@pytest.fixture
def model_module(monkeypatch):
    """Reload seniocare.model with a clean MODEL_*/OLLAMA_* environment."""
    for key in list(__import__("os").environ):
        if key.startswith(("MODEL_", "OLLAMA_")):
            monkeypatch.delenv(key, raising=False)

    def load(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        import seniocare.model as module
        return importlib.reload(module)

    return load


def test_defaults_are_local_ollama(model_module):
    m = model_module()
    s = m.model_settings()
    assert s["model"] == "ollama_chat/gemma4:e4b"
    assert "api_base" not in s and "api_key" not in s
    assert s["timeout"] == 120.0
    assert m.describe_model()["location"] == "local"
    assert m.probe_url() == "http://localhost:11434/api/tags"


def test_openai_compatible_remote_gets_placeholder_key(model_module):
    m = model_module(MODEL_NAME="openai/gemma4:e4b", MODEL_API_BASE="https://x.trycloudflare.com/v1/")
    s = m.model_settings()
    assert s["api_base"] == "https://x.trycloudflare.com/v1"  # trailing slash stripped
    assert s["api_key"] == "not-needed"  # the OpenAI client refuses an empty key
    assert m.describe_model()["location"] == "remote"
    assert m.probe_url() == "https://x.trycloudflare.com/v1/models"


def test_explicit_key_wins_over_placeholder(model_module):
    m = model_module(MODEL_NAME="openai/foo", MODEL_API_BASE="https://h/v1", MODEL_API_KEY="sk-real")
    assert m.model_settings()["api_key"] == "sk-real"
    assert m.describe_model()["api_key"] == "set"
    assert m.describe_model(mask_key=False)["api_key"] == "sk-real"


def test_ollama_chat_remote_does_not_get_placeholder_key(model_module):
    m = model_module(MODEL_NAME="ollama_chat/gemma4:e4b", MODEL_API_BASE="https://x.ngrok.app")
    s = m.model_settings()
    assert "api_key" not in s
    assert m.probe_url() == "https://x.ngrok.app/api/tags"


def test_provider_hosted_has_no_probe(model_module):
    m = model_module(MODEL_NAME="gemini/gemini-2.5-flash", MODEL_API_KEY="k")
    assert m.probe_url() is None
    assert m.describe_model()["location"] == "provider-hosted"


def test_sampling_parameters_and_extra_json(model_module):
    m = model_module(
        MODEL_TEMPERATURE="0.2",
        MODEL_MAX_TOKENS="1024",
        MODEL_TIMEOUT_S="60",
        MODEL_EXTRA_JSON=json.dumps({"top_p": 0.9, "num_ctx": 8192}),
    )
    s = m.model_settings()
    assert s["temperature"] == 0.2
    assert s["max_tokens"] == 1024
    assert s["timeout"] == 60.0
    assert s["top_p"] == 0.9 and s["num_ctx"] == 8192


def test_legacy_ollama_variables_still_work(model_module):
    m = model_module(OLLAMA_MODEL="ollama_chat/llama3.2", OLLAMA_BASE_URL="http://10.0.0.5:11434")
    s = m.model_settings()
    assert s["model"] == "ollama_chat/llama3.2"
    assert s["api_base"] == "http://10.0.0.5:11434"


def test_new_variables_take_precedence_over_legacy(model_module):
    m = model_module(MODEL_NAME="openai/new", OLLAMA_MODEL="ollama_chat/old")
    assert m.model_settings()["model"] == "openai/new"


@pytest.mark.parametrize(
    "env, message",
    [
        ({"MODEL_EXTRA_JSON": "{oops"}, "not valid JSON"),
        ({"MODEL_EXTRA_JSON": "[1,2]"}, "must be a JSON object"),
        ({"MODEL_TEMPERATURE": "warm"}, "must be a number"),
        ({"MODEL_MAX_TOKENS": "1.5"}, "must be an integer"),
    ],
)
def test_invalid_values_fail_loudly(model_module, env, message):
    m = model_module(**env)
    with pytest.raises(ValueError, match=message):
        m.model_settings()
