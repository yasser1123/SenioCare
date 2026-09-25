"""
================================================================================
                           WEB SEARCH TOOLS
                    SenioCare Elderly Healthcare Assistant
================================================================================

1. search_web()          - General web search with content extraction
2. search_youtube()      - YouTube videos for exercises and recipes
3. search_medical_info() - Medical search restricted to trusted sources

Providers (first one with a key wins; override with SEARCH_PROVIDER):
  - Tavily   (TAVILY_API_KEY)   web + medical; also YouTube via include_domains
  - SerpAPI  (SERPAPI_KEY)      web + medical + YouTube engine
  - YouTube Data API v3 (YOUTUBE_API_KEY), used for videos when set
With no key at all, search_medical_info falls back to a small local knowledge
base and the others return status "error" (the pipeline still answers).

During the evaluation no SerpAPI key was configured, so every search failed
(docs/RESULTS.md). Results can be cached on disk (SEARCH_CACHE_DIR) so that
repeated evaluation runs see identical search results and spend no credits.

Guards: each tool runs at most once per TURN (seniocare/tools/_guards.py).
The old session-lifetime booleans (``_web_search_called`` etc.) blocked every
search after the first one in a session: AUDIT C-04, masked here because
search never succeeded.
================================================================================
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google.adk.tools import ToolContext

from seniocare import observability as obs
from seniocare.tools._guards import guard

load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

# Keys come from the environment (.env). Never commit API keys.
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
SEARCH_PROVIDER = os.environ.get("SEARCH_PROVIDER", "").strip().lower()   # tavily | serpapi | "" (auto)
SEARCH_CACHE_DIR = os.environ.get("SEARCH_CACHE_DIR", "").strip()

TAVILY_URL = "https://api.tavily.com/search"
SERPAPI_URL = "https://serpapi.com/search"
YOUTUBE_URL = "https://www.googleapis.com/youtube/v3/search"

# Trusted medical sources (English and Arabic pages)
TRUSTED_MEDICAL_SOURCES = [
    "who.int",
    "mayoclinic.org",
    "medlineplus.gov",
    "nhs.uk",
    "nih.gov",
    "cdc.gov",
    "clevelandclinic.org",
    "webmd.com",
    "healthline.com",
]


def provider() -> Optional[str]:
    """The web-search provider in use, or None when no key is configured."""
    if SEARCH_PROVIDER == "tavily" and TAVILY_API_KEY:
        return "tavily"
    if SEARCH_PROVIDER == "serpapi" and SERPAPI_KEY:
        return "serpapi"
    if TAVILY_API_KEY:
        return "tavily"
    if SERPAPI_KEY:
        return "serpapi"
    return None


# =============================================================================
# HELPERS
# =============================================================================

def _cache_path(kind: str, payload: dict) -> Optional[Path]:
    if not SEARCH_CACHE_DIR:
        return None
    key = hashlib.sha256(json.dumps([kind, payload], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
    return Path(SEARCH_CACHE_DIR) / f"{kind}_{key}.json"


def _cached(kind: str, payload: dict, fetch) -> dict:
    """Return a cached successful result for (kind, payload), or fetch and cache it."""
    path = _cache_path(kind, payload)
    if path and path.exists():
        obs.emit("search_call", provider=kind, cached=True, ok=True, latency_ms=0, cost=0.0)
        return json.loads(path.read_text(encoding="utf-8"))
    result = fetch()
    if path and result.get("success"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def _post_tavily(payload: dict) -> dict:
    payload = {k: v for k, v in payload.items() if v is not None}

    def fetch():
        t0 = time.perf_counter()
        try:
            r = requests.post(TAVILY_URL, json=payload, timeout=20,
                              headers={"Authorization": f"Bearer {TAVILY_API_KEY}"})
            obs.emit("search_call", provider="tavily", http_status=r.status_code, cached=False,
                     latency_ms=round((time.perf_counter() - t0) * 1000), ok=r.status_code == 200, cost=0.0)
            if r.status_code != 200:
                return {"success": False, "error": f"Tavily HTTP {r.status_code}: {r.text[:200]}", "data": None}
            return {"success": True, "error": None, "data": r.json()}
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": f"Tavily request failed: {e}", "data": None}
    return _cached("tavily", payload, fetch)


def _search_serpapi(query: str, engine: str = "google", **kwargs) -> dict:
    """Performs a search using SerpAPI."""
    if not SERPAPI_KEY:
        return {"success": False, "error": "SERPAPI_KEY is not configured.", "data": None}

    payload = {"engine": engine, "q": query, **kwargs}

    def fetch():
        t0 = time.perf_counter()
        try:
            response = requests.get(SERPAPI_URL, params={**payload, "api_key": SERPAPI_KEY}, timeout=15)
            obs.emit("serpapi_call", engine=engine, http_status=response.status_code,
                     latency_ms=round((time.perf_counter() - t0) * 1000),
                     cost=obs.SERPAPI_USD_PER_SEARCH, ok=response.status_code == 200)
            data = response.json()
            if "error" in data:
                return {"success": False, "error": data["error"], "data": None}
            return {"success": True, "error": None, "data": data}
        except requests.exceptions.Timeout:
            return {"success": False, "error": "SerpAPI request timed out", "data": None}
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": f"SerpAPI request failed: {e}", "data": None}
    return _cached("serpapi", payload, fetch)


def _youtube_data_api(query: str, num_results: int, video_duration: Optional[str]) -> dict:
    payload = {"part": "snippet", "q": query, "type": "video", "maxResults": num_results,
               "regionCode": "EG", "relevanceLanguage": "ar", "safeSearch": "strict"}
    if video_duration in ("short", "medium", "long"):
        payload["videoDuration"] = video_duration

    def fetch():
        t0 = time.perf_counter()
        try:
            r = requests.get(YOUTUBE_URL, params={**payload, "key": YOUTUBE_API_KEY}, timeout=15)
            obs.emit("search_call", provider="youtube_api", http_status=r.status_code, cached=False,
                     latency_ms=round((time.perf_counter() - t0) * 1000), ok=r.status_code == 200, cost=0.0)
            if r.status_code != 200:
                return {"success": False, "error": f"YouTube API HTTP {r.status_code}", "data": None}
            return {"success": True, "error": None, "data": r.json()}
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": f"YouTube API request failed: {e}", "data": None}
    return _cached("youtube_api", payload, fetch)


def _video_id(url: str) -> str:
    if "v=" in url:
        return url.split("v=")[-1].split("&")[0]
    if "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0]
    if "/shorts/" in url:
        return url.split("/shorts/")[-1].split("?")[0]
    return ""


def _no_provider(query: str, key: str) -> dict:
    return {"status": "error", "query": query, key: [],
            "error": "No search API key configured (set TAVILY_API_KEY or SERPAPI_KEY in .env)."}


def _extract_content_from_url(url: str, max_length: int = 2000) -> dict:
    """
    Extracts the main text content from a URL using BeautifulSoup.
    
    Args:
        url: The URL to scrape content from.
        max_length: Maximum characters to extract (default 2000).
        
    Returns:
        dict: Contains 'success', 'content', and 'error' keys.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script, style, nav, footer, and ad elements
        for element in soup(['script', 'style', 'nav', 'footer', 'aside', 'header', 
                            'iframe', 'noscript', 'form']):
            element.decompose()
        
        # Try to find main content areas
        main_content = None
        for selector in ['main', 'article', '[role="main"]', '.content', '#content', 
                         '.post-content', '.article-body', '.entry-content']:
            main_content = soup.select_one(selector)
            if main_content:
                break
        
        # Fallback to body if no main content found
        if not main_content:
            main_content = soup.body
        
        if main_content:
            # Get text and clean it
            text = main_content.get_text(separator=' ', strip=True)
            # Remove extra whitespace
            text = ' '.join(text.split())
            # Truncate to max length
            if len(text) > max_length:
                text = text[:max_length] + "..."
            
            return {
                "success": True,
                "content": text,
                "error": None
            }
        else:
            return {
                "success": False,
                "content": None,
                "error": "Could not find main content on page"
            }
            
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "content": None,
            "error": "Request timed out"
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "content": None,
            "error": f"Request failed: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "content": None,
            "error": f"Content extraction failed: {str(e)}"
        }


# =============================================================================
# TOOL: GENERAL WEB SEARCH WITH CONTENT EXTRACTION
# =============================================================================

def search_web(
    query: str,
    tool_context: ToolContext,
    num_results: int = 3,
    extract_content: bool = True,
    language: str = "ar"
) -> dict:
    """
    Searches the web and optionally extracts content from result pages.

    Args:
        query: The search query (can be in Arabic or English).
        tool_context: The ADK tool context for state management.
        num_results: Number of results to return (1-5, default 3).
        extract_content: Whether to include page content (default True).
        language: Search language - 'ar' for Arabic, 'en' for English.

    Returns:
        dict: {"status": "success"|"no_results"|"error"|"already_called",
               "query": str, "results": [{"title", "url", "snippet", "content"}]}
    """
    if guard(tool_context.state, "_web_search_called"):
        return {"status": "already_called", "message": "تم استدعاء أداة البحث بالفعل. استخدم النتائج السابقة."}

    num_results = max(1, min(5, num_results))
    prov = provider()
    if prov is None:
        return _no_provider(query, "results")

    results = []
    if prov == "tavily":
        api = _post_tavily({"query": query, "max_results": num_results, "search_depth": "basic",
                            "country": "egypt" if language == "ar" else None})
        if not api["success"]:
            return {"status": "error", "query": query, "results": [], "error": api["error"]}
        for item in (api["data"] or {}).get("results", [])[:num_results]:
            results.append({"title": item.get("title", ""), "url": item.get("url", ""),
                            "snippet": (item.get("content") or "")[:300],
                            "content": (item.get("content") or "")[:2000]})
    else:
        hl, gl = ("ar", "eg") if language == "ar" else ("en", "us")
        api = _search_serpapi(query=query, engine="google", hl=hl, gl=gl, num=num_results)
        if not api["success"]:
            return {"status": "error", "query": query, "results": [], "error": api["error"]}
        for item in api["data"].get("organic_results", [])[:num_results]:
            result = {"title": item.get("title", ""), "url": item.get("link", ""), "snippet": item.get("snippet", "")}
            if extract_content and result["url"]:
                content_result = _extract_content_from_url(result["url"])
                result["content"] = content_result["content"] if content_result["success"] else result["snippet"]
            results.append(result)

    if not results:
        return {"status": "no_results", "query": query, "results": [],
                "message": "لم يتم العثور على نتائج. جرب صياغة مختلفة للسؤال."}
    return {"status": "success", "query": query, "provider": prov, "results": results, "total_found": len(results)}


# =============================================================================
# TOOL: YOUTUBE VIDEO SEARCH
# =============================================================================

def search_youtube(
    query: str,
    tool_context: ToolContext,
    num_results: int = 5,
    video_duration: Optional[str] = None,
    sort_by: str = "relevance"
) -> dict:
    """
    Searches YouTube for videos and returns structured results with links.

    Perfect for finding exercise videos, recipes and health tutorials for
    elderly users.

    Args:
        query: The search query (e.g., "تمارين لكبار السن" or "exercises for seniors").
        tool_context: The ADK tool context for state management.
        num_results: Number of videos to return (1-10, default 5).
        video_duration: Filter by duration - 'short' (<4 min), 'medium', 'long' (>20 min).
        sort_by: Sort order - 'relevance' (other values are ignored by some providers).

    Returns:
        dict: {"status", "query", "videos": [{"title", "url", "video_id", "channel",
               "description", "embed_url"}], "total_found"}
    """
    if guard(tool_context.state, "_youtube_search_called"):
        return {"status": "already_called", "message": "تم استدعاء بحث يوتيوب بالفعل. استخدم النتائج السابقة."}

    num_results = max(1, min(10, num_results))
    videos = []

    if YOUTUBE_API_KEY:
        source = "youtube_api"
        api = _youtube_data_api(query, num_results, video_duration)
        if api["success"]:
            for item in (api["data"] or {}).get("items", [])[:num_results]:
                vid = (item.get("id") or {}).get("videoId", "")
                sn = item.get("snippet") or {}
                videos.append({"title": sn.get("title", ""), "url": f"https://www.youtube.com/watch?v={vid}",
                               "video_id": vid, "channel": sn.get("channelTitle", ""),
                               "published": sn.get("publishedAt", ""), "description": sn.get("description", "")})
    else:
        source = provider()
        if source is None:
            return _no_provider(query, "videos")
        if source == "tavily":
            api = _post_tavily({"query": query, "max_results": num_results, "include_domains": ["youtube.com"]})
            if api["success"]:
                for item in (api["data"] or {}).get("results", []):
                    url = item.get("url", "")
                    vid = _video_id(url)
                    if vid:
                        videos.append({"title": item.get("title", ""), "url": url, "video_id": vid,
                                       "channel": "", "description": (item.get("content") or "")[:300]})
        else:
            params = {"hl": "ar", "gl": "eg"}
            duration_filters = {"short": "EgIYAQ%3D%3D", "medium": "EgIYAw%3D%3D", "long": "EgIYAg%3D%3D"}
            if video_duration in duration_filters:
                params["sp"] = duration_filters[video_duration]
            api = _search_serpapi(query=query, engine="youtube", **params)
            if api["success"]:
                for item in api["data"].get("video_results", [])[:num_results]:
                    url = item.get("link", "")
                    channel = item.get("channel")
                    length = item.get("length")
                    videos.append({"title": item.get("title", ""), "url": url, "video_id": _video_id(url),
                                   "channel": channel.get("name", "") if isinstance(channel, dict) else "",
                                   "duration": length.get("simpleText", "") if isinstance(length, dict) else "",
                                   "description": item.get("description", "")})

    if not api["success"]:
        return {"status": "error", "query": query, "videos": [], "error": api["error"]}
    videos = videos[:num_results]
    for v in videos:
        if v.get("video_id"):
            v["embed_url"] = f"https://www.youtube.com/embed/{v['video_id']}"
    if not videos:
        return {"status": "no_results", "query": query, "videos": [],
                "message": "لم يتم العثور على فيديوهات. جرب كلمات بحث مختلفة."}
    return {"status": "success", "query": query, "provider": source, "videos": videos, "total_found": len(videos),
            "filters_applied": {"duration": video_duration, "sort": sort_by}}


# =============================================================================
# TOOL: MEDICAL INFORMATION SEARCH (TRUSTED SOURCES)
# =============================================================================

def search_medical_info(
    query: str,
    tool_context: ToolContext,
    prefer_trusted_sources: bool = True
) -> dict:
    """
    Searches for medical information from trusted medical sources (WHO, Mayo
    Clinic, MedlinePlus, NHS, NIH, CDC...), with source citations.

    Args:
        query: The medical question or topic to search for.
        tool_context: The ADK tool context for state management.
        prefer_trusted_sources: Restrict results to trusted medical sites (default True).

    Returns:
        dict: Search results with medical information and source citations.
    """
    if guard(tool_context.state, "_medical_search_called"):
        return {"status": "already_called", "message": "تم استدعاء البحث الطبي بالفعل. استخدم النتائج السابقة."}

    prov = provider()
    results = []
    if prov == "tavily":
        payload = {"query": query, "max_results": 3, "search_depth": "basic"}
        if prefer_trusted_sources:
            payload["include_domains"] = TRUSTED_MEDICAL_SOURCES
        api = _post_tavily(payload)
        if not api["success"]:
            return _fallback_medical_search(query)
        for item in (api["data"] or {}).get("results", [])[:3]:
            url = item.get("url", "")
            results.append({"title": item.get("title", ""), "url": url,
                            "snippet": (item.get("content") or "")[:300],
                            "full_content": (item.get("content") or "")[:1500],
                            "source": url.split("/")[2] if "//" in url else "Unknown",
                            "is_trusted_source": any(s in url for s in TRUSTED_MEDICAL_SOURCES)})
    elif prov == "serpapi":
        medical_query = query
        if prefer_trusted_sources:
            site_query = " OR ".join(f"site:{site}" for site in TRUSTED_MEDICAL_SOURCES[:5])
            medical_query = f"({query}) ({site_query})"
        api = _search_serpapi(query=medical_query, engine="google", hl="en", gl="us", num=5)
        if not api["success"]:
            return _fallback_medical_search(query)
        for item in api["data"].get("organic_results", [])[:3]:
            url = item.get("link", "")
            is_trusted = any(source in url for source in TRUSTED_MEDICAL_SOURCES)
            result = {"title": item.get("title", ""), "url": url, "snippet": item.get("snippet", ""),
                      "source": url.split("/")[2] if url else "Unknown", "is_trusted_source": is_trusted}
            if is_trusted:
                content_result = _extract_content_from_url(url, max_length=1500)
                if content_result["success"]:
                    result["full_content"] = content_result["content"]
            results.append(result)
    else:
        return _fallback_medical_search(query)

    if not results:
        return _fallback_medical_search(query)
    return {
        "status": "success",
        "query": query,
        "provider": prov,
        "results": results,
        "disclaimer": "هذه المعلومات للتثقيف فقط وليست بديلاً عن استشارة الطبيب. يُرجى مراجعة طبيبك للحصول على نصيحة طبية شخصية.",
        "sources_used": [r["source"] for r in results],
    }


def _fallback_medical_search(query: str) -> dict:
    """
    Fallback to local knowledge base when API fails.
    """
    knowledge_base = {
        "diabetes": {
            "summary": "مرض السكري هو حالة تؤثر على كيفية تعامل الجسم مع سكر الدم (الجلوكوز).",
            "key_points": [
                "حافظ على مستوى السكر في الدم بين 80-130 قبل الوجبات",
                "تناول الأدوية في مواعيدها المحددة",
                "تجنب السكريات والنشويات الزائدة",
                "مارس المشي الخفيف يومياً"
            ],
            "when_to_see_doctor": [
                "إذا كان مستوى السكر أعلى من 300 أو أقل من 70",
                "إذا شعرت بعطش شديد أو تبول متكرر",
                "إذا شعرت بدوخة أو ارتباك"
            ],
            "source": "Mayo Clinic, WHO Guidelines"
        },
        "hypertension": {
            "summary": "ارتفاع ضغط الدم هو حالة يكون فيها ضغط الدم مرتفعاً باستمرار.",
            "key_points": [
                "الضغط الطبيعي أقل من 120/80",
                "قلل من الملح في الطعام",
                "تجنب التوتر والإجهاد",
                "تناول أدوية الضغط بانتظام"
            ],
            "when_to_see_doctor": [
                "إذا كان الضغط أعلى من 180/120",
                "إذا شعرت بصداع شديد مفاجئ",
                "إذا شعرت بألم في الصدر أو ضيق في التنفس"
            ],
            "source": "American Heart Association, WHO"
        },
        "arthritis": {
            "summary": "التهاب المفاصل هو التهاب في واحد أو أكثر من المفاصل.",
            "key_points": [
                "حافظ على وزن صحي لتقليل الضغط على المفاصل",
                "مارس تمارين خفيفة بانتظام",
                "استخدم الكمادات الدافئة لتخفيف الألم",
                "تناول أدوية الالتهاب حسب وصفة الطبيب"
            ],
            "when_to_see_doctor": [
                "إذا زاد الألم بشكل كبير",
                "إذا لاحظت تورماً أو احمراراً جديداً",
                "إذا لم تستطع تحريك المفصل"
            ],
            "source": "Arthritis Foundation, NIH"
        }
    }
    
    # Simple keyword matching
    query_lower = query.lower()
    results = []
    
    for topic, info in knowledge_base.items():
        if topic in query_lower or any(word in query_lower for word in topic.split()):
            results.append({
                "topic": topic,
                "information": info
            })
    
    if results:
        return {
            "status": "success",
            "source": "local_knowledge_base",
            "results": results,
            "disclaimer": "هذه المعلومات للتثقيف فقط وليست بديلاً عن استشارة الطبيب"
        }
    else:
        return {
            "status": "no_results",
            "message": "لم نجد معلومات محددة. يُرجى استشارة طبيبك للحصول على معلومات دقيقة.",
            "suggestion": "جرب البحث عن: السكري، ضغط الدم، التهاب المفاصل"
        }
