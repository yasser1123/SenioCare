"""Search providers (Tavily / SerpAPI / YouTube Data API), per-turn guards and the on-disk cache. No network."""

import json

import pytest

import seniocare.tools.web_search as ws


class Ctx:
    def __init__(self, turn=1):
        self.state = {"conversation_turn_count": turn}


class Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code, self.text = data, status, json.dumps(data)

    def json(self):
        return self._data


@pytest.fixture
def tavily(monkeypatch):
    calls = []

    def post(url, json=None, headers=None, timeout=None):
        calls.append(json)
        if json.get("include_domains") == ["youtube.com"]:
            return Resp({"results": [{"title": "تمارين كرسي", "url": "https://www.youtube.com/watch?v=abc123", "content": "x"},
                                     {"title": "not a video", "url": "https://www.youtube.com/@channel", "content": "y"}]})
        return Resp({"results": [{"title": "Diabetes - WHO", "url": "https://www.who.int/news-room/fact-sheets/detail/diabetes",
                                  "content": "Diabetes is a chronic disease..."}]})

    monkeypatch.setattr(ws, "TAVILY_API_KEY", "tvly-test")
    monkeypatch.setattr(ws, "SERPAPI_KEY", "")
    monkeypatch.setattr(ws, "YOUTUBE_API_KEY", "")
    monkeypatch.setattr(ws, "SEARCH_PROVIDER", "")
    monkeypatch.setattr(ws, "SEARCH_CACHE_DIR", "")
    monkeypatch.setattr(ws.requests, "post", post)
    return calls


def test_no_key_means_error_and_local_fallback(monkeypatch):
    for k in ("TAVILY_API_KEY", "SERPAPI_KEY", "YOUTUBE_API_KEY"):
        monkeypatch.setattr(ws, k, "")
    assert ws.provider() is None
    assert ws.search_web("x", Ctx())["status"] == "error"
    assert ws.search_youtube("x", Ctx())["status"] == "error"
    assert ws.search_medical_info("diabetes", Ctx())["source"] == "local_knowledge_base"


def test_medical_search_is_restricted_to_trusted_domains(tavily):
    out = ws.search_medical_info("diabetes diet", Ctx())
    assert out["status"] == "success" and out["provider"] == "tavily"
    assert tavily[0]["include_domains"] == ws.TRUSTED_MEDICAL_SOURCES
    assert out["results"][0]["is_trusted_source"] and out["sources_used"] == ["www.who.int"]


def test_youtube_via_tavily_keeps_only_video_links(tavily):
    out = ws.search_youtube("تمارين لكبار السن", Ctx())
    assert [v["video_id"] for v in out["videos"]] == ["abc123"]
    assert out["videos"][0]["embed_url"].endswith("/abc123")


def test_guard_is_per_turn_not_per_session(tavily):
    ctx = Ctx(turn=1)
    assert ws.search_web("q", ctx)["status"] == "success"
    assert ws.search_web("q", ctx)["status"] == "already_called"
    ctx.state["conversation_turn_count"] = 2          # next turn in the same session
    assert ws.search_web("q", ctx)["status"] == "success"


def test_cache_replays_identical_results_without_calling_the_api(tavily, monkeypatch, tmp_path):
    monkeypatch.setattr(ws, "SEARCH_CACHE_DIR", str(tmp_path))
    first = ws.search_medical_info("hypertension", Ctx(1))
    second = ws.search_medical_info("hypertension", Ctx(2))
    assert first == second and len(tavily) == 1


def test_youtube_data_api_is_used_when_its_key_is_set(tavily, monkeypatch):
    monkeypatch.setattr(ws, "YOUTUBE_API_KEY", "yt-test")
    monkeypatch.setattr(ws.requests, "get", lambda url, params=None, timeout=None: Resp(
        {"items": [{"id": {"videoId": "v1"}, "snippet": {"title": "t", "channelTitle": "c"}}]}))
    out = ws.search_youtube("q", Ctx())
    assert out["provider"] == "youtube_api" and out["videos"][0]["url"].endswith("v=v1")
