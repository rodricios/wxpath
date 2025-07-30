#!/usr/bin/env python3
"""
Quick test script for async_core.py implementation.
"""

import asyncio
import time
from wxpath.async_core import async_wxpath, async_fetch_html_batch
from wxpath.crawler import Crawler


async def test_async_fetch_batch():
    """Test the batch fetching functionality."""
    print("Testing async_fetch_html_batch...")
    
    urls = [
        "https://httpbin.org/delay/1",
        "https://httpbin.org/delay/1", 
        "https://httpbin.org/status/200",
        "https://httpbin.org/status/404",  # This should fail gracefully
        "https://httpbin.org/json"
    ]
    
    crawler = Crawler(concurrency=3, per_host=2, timeout=10)
    
    start_time = time.time()
    results = await async_fetch_html_batch(urls, crawler)
    end_time = time.time()
    
    print(f"Batch fetch completed in {end_time - start_time:.2f} seconds")
    print(f"Successful fetches: {len([v for v in results.values() if v is not None])}/{len(urls)}")
    
    for url, content in results.items():
        if content:
            print(f"✅ {url}: {len(content)} bytes")
        else:
            print(f"❌ {url}: Failed")


async def test_simple_async_wxpath():
    """Test basic async wxpath functionality."""
    print("\nTesting simple async wxpath...")
    
    try:
        # Test with a simple URL
        results = []
        async for result in async_wxpath("https://httpbin.org/html", "//h1/text()"):
            results.append(result)
            
        print(f"Found {len(results)} results from wxpath expression")
        for i, result in enumerate(results[:3]):  # Show first 3 results
            print(f"  Result {i+1}: {result}")
            
    except Exception as e:
        print(f"Error in async wxpath test: {e}")


async def main():
    """Run all async tests."""
    print("Starting async_core.py tests...\n")
    
    try:
        await test_async_fetch_batch()
        await test_simple_async_wxpath()
        print("\n✅ All tests completed!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())