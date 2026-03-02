"""
Test script for the new web search tools.
"""

import json

# Mock ToolContext for testing
class MockToolContext:
    def __init__(self):
        self.state = {}

# Import tools
from seniocare.tools.web_search import search_web, search_youtube, search_medical_info

def test_youtube_search():
    """Test YouTube video search"""
    print("=" * 60)
    print("Testing YouTube Search Tool")
    print("=" * 60)
    
    ctx = MockToolContext()
    result = search_youtube(
        query="تمارين لكبار السن",
        tool_context=ctx,
        num_results=3,
        video_duration="medium"  # 4-20 minutes
    )
    
    print(f"\nStatus: {result.get('status')}")
    print(f"Query: {result.get('query')}")
    print(f"Total videos found: {result.get('total_found')}")
    
    if result.get('videos'):
        print("\nVideos:")
        for i, video in enumerate(result['videos'], 1):
            print(f"\n  {i}. {video.get('title')}")
            print(f"     URL: {video.get('url')}")
            print(f"     Channel: {video.get('channel')}")
            print(f"     Duration: {video.get('duration')}")
    else:
        print(f"\nError: {result.get('error', result.get('message', 'Unknown error'))}")
    
    return result

def test_web_search():
    """Test general web search with content extraction"""
    print("\n" + "=" * 60)
    print("Testing Web Search Tool (with content extraction)")
    print("=" * 60)
    
    ctx = MockToolContext()
    result = search_web(
        query="diabetes management tips for elderly",
        tool_context=ctx,
        num_results=2,
        extract_content=True,
        language="en"
    )
    
    print(f"\nStatus: {result.get('status')}")
    print(f"Query: {result.get('query')}")
    print(f"Total results: {result.get('total_found')}")
    
    if result.get('results'):
        print("\nResults:")
        for i, res in enumerate(result['results'], 1):
            print(f"\n  {i}. {res.get('title')}")
            print(f"     URL: {res.get('url')}")
            print(f"     Snippet: {res.get('snippet', '')[:100]}...")
            if res.get('content'):
                print(f"     Content (first 200 chars): {res.get('content', '')[:200]}...")
    else:
        print(f"\nError: {result.get('error', result.get('message', 'Unknown error'))}")
    
    return result

def test_medical_search():
    """Test medical information search"""
    print("\n" + "=" * 60)
    print("Testing Medical Info Search Tool")
    print("=" * 60)
    
    ctx = MockToolContext()
    result = search_medical_info(
        query="hypertension blood pressure management",
        tool_context=ctx,
        prefer_trusted_sources=True
    )
    
    print(f"\nStatus: {result.get('status')}")
    print(f"Query: {result.get('query', 'N/A')}")
    
    if result.get('results'):
        print(f"Sources used: {result.get('sources_used', [])}")
        print("\nResults:")
        for i, res in enumerate(result['results'], 1):
            if isinstance(res, dict):
                if 'topic' in res:  # Fallback format
                    print(f"\n  {i}. Topic: {res.get('topic')}")
                    print(f"     Summary: {res.get('information', {}).get('summary', '')}")
                else:  # API format
                    print(f"\n  {i}. {res.get('title')}")
                    print(f"     Source: {res.get('source')}")
                    print(f"     Trusted: {res.get('is_trusted_source')}")
                    print(f"     Snippet: {res.get('snippet', '')[:150]}...")
    else:
        print(f"\nError: {result.get('error', result.get('message', 'Unknown error'))}")
    
    print(f"\nDisclaimer: {result.get('disclaimer', 'N/A')}")
    
    return result


if __name__ == "__main__":
    print("\n🔍 SenioCare Web Search Tools Test\n")
    
    # Test YouTube search
    youtube_result = test_youtube_search()
    
    # Test web search
    web_result = test_web_search()
    
    # Test medical search
    medical_result = test_medical_search()
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)
    
    # Summary
    print("\n📊 Summary:")
    print(f"  - YouTube Search: {youtube_result.get('status')}")
    print(f"  - Web Search: {web_result.get('status')}")
    print(f"  - Medical Search: {medical_result.get('status')}")
