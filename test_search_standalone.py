"""
Standalone test script for the SerpAPI web search functions.
This test does not require Google ADK.
"""

import requests
from bs4 import BeautifulSoup
import json

# =============================================================================
# CONFIGURATION
# =============================================================================

SERPAPI_KEY = "fa3aa24b0ed25e473b7ef9ae408ea9df683a910d12e8d5b21853f729a436e39f"
SERPAPI_URL = "https://serpapi.com/search"


# =============================================================================
# MOCK TOOL CONTEXT
# =============================================================================

class MockToolContext:
    """Mock ToolContext for testing without ADK"""
    def __init__(self):
        self.state = {}


# =============================================================================
# TEST FUNCTIONS
# =============================================================================

def test_serpapi_connection():
    """Test basic SerpAPI connection"""
    print("=" * 60)
    print("Testing SerpAPI Connection")
    print("=" * 60)
    
    params = {
        "engine": "google",
        "q": "test query",
        "api_key": SERPAPI_KEY,
        "num": 1
    }
    
    try:
        response = requests.get(SERPAPI_URL, params=params, timeout=15)
        data = response.json()
        
        if "error" in data:
            print(f"❌ API Error: {data['error']}")
            return False
        
        print("✅ SerpAPI connection successful!")
        print(f"   Search metadata: {data.get('search_metadata', {}).get('status', 'N/A')}")
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {str(e)}")
        return False


def test_youtube_search():
    """Test YouTube video search via SerpAPI"""
    print("\n" + "=" * 60)
    print("Testing YouTube Search")
    print("=" * 60)
    
    params = {
        "engine": "youtube",
        "search_query": "تمارين لكبار السن",  # Exercises for elderly in Arabic
        "api_key": SERPAPI_KEY,
        "hl": "ar",
        "gl": "eg"
    }
    
    try:
        response = requests.get(SERPAPI_URL, params=params, timeout=15)
        data = response.json()
        
        if "error" in data:
            print(f"❌ API Error: {data['error']}")
            return None
        
        video_results = data.get("video_results", [])
        
        print(f"✅ Found {len(video_results)} videos")
        
        videos = []
        for i, item in enumerate(video_results[:3], 1):
            video_id = item.get("link", "").split("v=")[-1].split("&")[0]
            video = {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "video_id": video_id,
                "channel": item.get("channel", {}).get("name", "") if isinstance(item.get("channel"), dict) else "",
                "duration": item.get("length", {}).get("simpleText", "") if isinstance(item.get("length"), dict) else item.get("duration", ""),
                "views": item.get("views", ""),
                "thumbnail": item.get("thumbnail", {}).get("static", "") if isinstance(item.get("thumbnail"), dict) else item.get("thumbnail", "")
            }
            videos.append(video)
            
            print(f"\n   {i}. {video['title']}")
            print(f"      URL: {video['url']}")
            print(f"      Channel: {video['channel']}")
            print(f"      Duration: {video['duration']}")
        
        return {
            "status": "success",
            "videos": videos,
            "total_found": len(videos)
        }
        
    except Exception as e:
        print(f"❌ YouTube search failed: {str(e)}")
        return None


def test_web_search():
    """Test general web search via SerpAPI"""
    print("\n" + "=" * 60)
    print("Testing Web Search")
    print("=" * 60)
    
    params = {
        "engine": "google",
        "q": "diabetes management tips for seniors",
        "api_key": SERPAPI_KEY,
        "hl": "en",
        "gl": "us",
        "num": 3
    }
    
    try:
        response = requests.get(SERPAPI_URL, params=params, timeout=15)
        data = response.json()
        
        if "error" in data:
            print(f"❌ API Error: {data['error']}")
            return None
        
        organic_results = data.get("organic_results", [])
        
        print(f"✅ Found {len(organic_results)} results")
        
        results = []
        for i, item in enumerate(organic_results[:3], 1):
            result = {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "source": item.get("link", "").split("/")[2] if item.get("link") else ""
            }
            results.append(result)
            
            print(f"\n   {i}. {result['title']}")
            print(f"      URL: {result['url']}")
            print(f"      Snippet: {result['snippet'][:100]}...")
        
        return {
            "status": "success",
            "results": results,
            "total_found": len(results)
        }
        
    except Exception as e:
        print(f"❌ Web search failed: {str(e)}")
        return None


def test_content_extraction():
    """Test BeautifulSoup content extraction"""
    print("\n" + "=" * 60)
    print("Testing Content Extraction (BeautifulSoup)")
    print("=" * 60)
    
    # Test with Mayo Clinic
    test_url = "https://www.mayoclinic.org/diseases-conditions/diabetes/symptoms-causes/syc-20371444"
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(test_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove unwanted elements
        for element in soup(['script', 'style', 'nav', 'footer', 'aside', 'header']):
            element.decompose()
        
        # Find main content
        main_content = None
        for selector in ['main', 'article', '.content', '#content']:
            main_content = soup.select_one(selector)
            if main_content:
                break
        
        if not main_content:
            main_content = soup.body
        
        if main_content:
            text = main_content.get_text(separator=' ', strip=True)
            text = ' '.join(text.split())[:500]  # First 500 chars
            
            print(f"✅ Successfully extracted content from Mayo Clinic")
            print(f"   URL: {test_url}")
            print(f"   Content preview: {text[:300]}...")
            
            return {
                "status": "success",
                "content": text
            }
        else:
            print("❌ Could not find main content")
            return None
            
    except Exception as e:
        print(f"❌ Content extraction failed: {str(e)}")
        return None


def print_json_output(result: dict, title: str):
    """Print formatted JSON output"""
    print(f"\n📄 {title} JSON Output:")
    print("-" * 40)
    print(json.dumps(result, indent=2, ensure_ascii=False)[:1000])
    if len(json.dumps(result)) > 1000:
        print("... (truncated)")


if __name__ == "__main__":
    print("\n🔍 SenioCare Web Search Tools - Standalone Test\n")
    
    # Track results
    all_passed = True
    
    # Test 1: SerpAPI Connection
    if not test_serpapi_connection():
        all_passed = False
    
    # Test 2: YouTube Search
    youtube_result = test_youtube_search()
    if youtube_result:
        print_json_output(youtube_result, "YouTube Search")
    else:
        all_passed = False
    
    # Test 3: Web Search
    web_result = test_web_search()
    if web_result:
        print_json_output(web_result, "Web Search")
    else:
        all_passed = False
    
    # Test 4: Content Extraction
    content_result = test_content_extraction()
    if content_result:
        print_json_output(content_result, "Content Extraction")
    else:
        all_passed = False
    
    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All tests passed! Tools are ready to use.")
    else:
        print("⚠️ Some tests failed. Check the output above.")
    print("=" * 60)
