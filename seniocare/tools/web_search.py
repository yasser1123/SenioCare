"""
================================================================================
                           WEB SEARCH TOOLS
                    SenioCare Elderly Healthcare Assistant
================================================================================

This module provides web search capabilities for the SenioCare assistant:

1. search_web()          - General web search with content extraction
2. search_youtube()      - YouTube video search for exercise/health videos
3. search_medical_info() - Medical-focused search with trusted sources

All tools use SerpAPI for search functionality and BeautifulSoup for 
content extraction when needed.

================================================================================
"""

import requests
from bs4 import BeautifulSoup
from typing import Optional
from google.adk.tools import ToolContext

# =============================================================================
# CONFIGURATION
# =============================================================================

SERPAPI_KEY = "fa3aa24b0ed25e473b7ef9ae408ea9df683a910d12e8d5b21853f729a436e39f"
SERPAPI_URL = "https://serpapi.com/search"

# Trusted medical sources for filtering
TRUSTED_MEDICAL_SOURCES = [
    "mayoclinic.org",
    "webmd.com",
    "healthline.com",
    "nih.gov",
    "who.int",
    "cdc.gov",
    "medlineplus.gov",
    "clevelandclinic.org",
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

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


def _search_serpapi(query: str, engine: str = "google", **kwargs) -> dict:
    """
    Performs a search using SerpAPI.
    
    Args:
        query: The search query.
        engine: Search engine to use ('google', 'youtube', etc.).
        **kwargs: Additional parameters for the API.
        
    Returns:
        dict: The API response or error information.
    """
    params = {
        "engine": engine,
        "q": query,
        "api_key": SERPAPI_KEY,
        **kwargs
    }
    
    try:
        response = requests.get(SERPAPI_URL, params=params, timeout=15)
        data = response.json()
        
        if "error" in data:
            return {
                "success": False,
                "error": data["error"],
                "data": None
            }
        
        return {
            "success": True,
            "error": None,
            "data": data
        }
        
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "SerpAPI request timed out",
            "data": None
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"SerpAPI request failed: {str(e)}",
            "data": None
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
    
    This tool performs a Google search via SerpAPI and can scrape the main
    content from the top results using BeautifulSoup.
    
    Args:
        query: The search query (can be in Arabic or English).
        tool_context: The ADK tool context for state management.
        num_results: Number of results to return (1-5, default 3).
        extract_content: Whether to scrape content from URLs (default True).
        language: Search language - 'ar' for Arabic, 'en' for English.
        
    Returns:
        dict: Search results with the following structure:
            {
                "status": "success" | "error" | "already_called",
                "query": str,
                "results": [
                    {
                        "title": str,
                        "url": str,
                        "snippet": str,
                        "content": str (if extract_content=True)
                    }
                ],
                "error": str (if status="error")
            }
    """
    # Prevent multiple calls in the same turn
    if tool_context.state.get("_web_search_called"):
        return {
            "status": "already_called",
            "message": "تم استدعاء أداة البحث بالفعل. استخدم النتائج السابقة."
        }
    tool_context.state["_web_search_called"] = True
    
    # Validate num_results
    num_results = max(1, min(5, num_results))
    
    # Set language parameters
    hl = "ar" if language == "ar" else "en"
    gl = "eg" if language == "ar" else "us"
    
    # Perform search
    api_result = _search_serpapi(
        query=query,
        engine="google",
        hl=hl,
        gl=gl,
        num=num_results
    )
    
    if not api_result["success"]:
        return {
            "status": "error",
            "query": query,
            "results": [],
            "error": api_result["error"]
        }
    
    # Parse organic results
    organic_results = api_result["data"].get("organic_results", [])
    
    if not organic_results:
        return {
            "status": "no_results",
            "query": query,
            "results": [],
            "message": "لم يتم العثور على نتائج. جرب صياغة مختلفة للسؤال."
        }
    
    # Process results
    results = []
    for item in organic_results[:num_results]:
        result = {
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
        }
        
        # Extract content if requested
        if extract_content and result["url"]:
            content_result = _extract_content_from_url(result["url"])
            if content_result["success"]:
                result["content"] = content_result["content"]
            else:
                result["content"] = result["snippet"]  # Fallback to snippet
                result["content_error"] = content_result["error"]
        
        results.append(result)
    
    return {
        "status": "success",
        "query": query,
        "results": results,
        "total_found": len(results)
    }


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
    
    Perfect for finding exercise videos, health tutorials, and educational
    content for elderly users.
    
    Args:
        query: The search query (e.g., "تمارين لكبار السن" or "exercises for seniors").
        tool_context: The ADK tool context for state management.
        num_results: Number of videos to return (1-10, default 5).
        video_duration: Filter by duration - 'short' (<4 min), 'medium', 'long' (>20 min).
        sort_by: Sort order - 'relevance', 'date', 'view_count', 'rating'.
        
    Returns:
        dict: YouTube search results with the following structure:
            {
                "status": "success" | "error",
                "query": str,
                "videos": [
                    {
                        "title": str,
                        "url": str,
                        "video_id": str,
                        "thumbnail": str,
                        "channel": str,
                        "duration": str,
                        "views": str,
                        "published": str,
                        "description": str
                    }
                ],
                "total_found": int
            }
    """
    # Prevent multiple calls in the same turn
    if tool_context.state.get("_youtube_search_called"):
        return {
            "status": "already_called",
            "message": "تم استدعاء بحث يوتيوب بالفعل. استخدم النتائج السابقة."
        }
    tool_context.state["_youtube_search_called"] = True
    
    # Validate num_results
    num_results = max(1, min(10, num_results))
    
    # Build search parameters
    params = {
        "hl": "ar",  # Arabic interface
        "gl": "eg",  # Egypt region
    }
    
    # Add duration filter using sp parameter
    # These are YouTube's encoded filter values
    duration_filters = {
        "short": "EgIYAQ%3D%3D",      # Under 4 minutes
        "medium": "EgIYAw%3D%3D",     # 4-20 minutes  
        "long": "EgIYAg%3D%3D"        # Over 20 minutes
    }
    
    if video_duration and video_duration in duration_filters:
        params["sp"] = duration_filters[video_duration]
    
    # Perform YouTube search
    api_result = _search_serpapi(
        query=query,
        engine="youtube",
        **params
    )
    
    if not api_result["success"]:
        return {
            "status": "error",
            "query": query,
            "videos": [],
            "error": api_result["error"]
        }
    
    # Parse video results
    video_results = api_result["data"].get("video_results", [])
    
    if not video_results:
        return {
            "status": "no_results",
            "query": query,
            "videos": [],
            "message": "لم يتم العثور على فيديوهات. جرب كلمات بحث مختلفة."
        }
    
    # Process and structure video results
    videos = []
    for item in video_results[:num_results]:
        video_id = item.get("link", "").split("v=")[-1].split("&")[0] if item.get("link") else ""
        
        video = {
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "video_id": video_id,
            "thumbnail": item.get("thumbnail", {}).get("static", "") if isinstance(item.get("thumbnail"), dict) else item.get("thumbnail", ""),
            "channel": item.get("channel", {}).get("name", "") if isinstance(item.get("channel"), dict) else "",
            "duration": item.get("length", {}).get("simpleText", "") if isinstance(item.get("length"), dict) else item.get("duration", ""),
            "views": item.get("views", ""),
            "published": item.get("published_date", ""),
            "description": item.get("description", "")
        }
        
        # Generate embed URL for easy embedding in apps
        if video_id:
            video["embed_url"] = f"https://www.youtube.com/embed/{video_id}"
        
        videos.append(video)
    
    return {
        "status": "success",
        "query": query,
        "videos": videos,
        "total_found": len(videos),
        "filters_applied": {
            "duration": video_duration,
            "sort": sort_by
        }
    }


# =============================================================================
# TOOL: MEDICAL INFORMATION SEARCH (ENHANCED WITH SERPAPI)
# =============================================================================

def search_medical_info(
    query: str,
    tool_context: ToolContext,
    prefer_trusted_sources: bool = True
) -> dict:
    """
    Searches for medical information, prioritizing trusted medical sources.
    
    This tool combines SerpAPI search with content extraction, filtering
    results to prefer trusted medical websites like Mayo Clinic, WebMD,
    NIH, and WHO.
    
    Args:
        query: The medical question or topic to search for.
        tool_context: The ADK tool context for state management.
        prefer_trusted_sources: Whether to prioritize trusted medical sites (default True).
        
    Returns:
        dict: Search results with medical information and source citations.
    """
    # Prevent multiple calls in the same turn
    if tool_context.state.get("_medical_search_called"):
        return {
            "status": "already_called",
            "message": "تم استدعاء البحث الطبي بالفعل. استخدم النتائج السابقة."
        }
    tool_context.state["_medical_search_called"] = True
    
    # Enhance query for medical focus
    medical_query = f"{query} medical health information"
    
    # If preferring trusted sources, add site restrictions
    if prefer_trusted_sources:
        # Search across trusted medical sites
        site_query = " OR ".join([f"site:{site}" for site in TRUSTED_MEDICAL_SOURCES[:4]])
        medical_query = f"({query}) ({site_query})"
    
    # Perform search
    api_result = _search_serpapi(
        query=medical_query,
        engine="google",
        hl="en",  # Medical info often better in English
        gl="us",
        num=5
    )
    
    if not api_result["success"]:
        # Fallback to local knowledge base
        return _fallback_medical_search(query)
    
    # Parse organic results
    organic_results = api_result["data"].get("organic_results", [])
    
    if not organic_results:
        return _fallback_medical_search(query)
    
    # Process results with content extraction
    results = []
    for item in organic_results[:3]:
        url = item.get("link", "")
        
        # Check if from trusted source
        is_trusted = any(source in url for source in TRUSTED_MEDICAL_SOURCES)
        
        result = {
            "title": item.get("title", ""),
            "url": url,
            "snippet": item.get("snippet", ""),
            "source": url.split("/")[2] if url else "Unknown",
            "is_trusted_source": is_trusted
        }
        
        # Extract content from trusted sources
        if is_trusted:
            content_result = _extract_content_from_url(url, max_length=1500)
            if content_result["success"]:
                result["full_content"] = content_result["content"]
        
        results.append(result)
    
    return {
        "status": "success",
        "query": query,
        "results": results,
        "disclaimer": "هذه المعلومات للتثقيف فقط وليست بديلاً عن استشارة الطبيب. يُرجى مراجعة طبيبك للحصول على نصيحة طبية شخصية.",
        "sources_used": [r["source"] for r in results]
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
