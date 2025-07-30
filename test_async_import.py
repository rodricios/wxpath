#!/usr/bin/env python3
"""
Test async_core import with optional aiohttp dependency.
"""

try:
    # Try to import aiohttp first
    try:
        import aiohttp
        print("✅ aiohttp is available")
        aiohttp_available = True
    except ImportError:
        print("❌ aiohttp not available - this is expected if not installed")
        aiohttp_available = False
    
    if aiohttp_available:
        # Only try to import async_core if aiohttp is available
        try:
            from wxpath.async_core import async_wxpath, async_fetch_html_batch
            print("✅ Successfully imported async_core functions")
            print("✅ async_core.py implementation is syntactically correct")
        except Exception as e:
            print(f"❌ Error importing async_core: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("ℹ️  Skipping async_core import test due to missing aiohttp")
        # Let's check if the file exists and has basic syntax
        try:
            with open('wxpath/async_core.py', 'r') as f:
                content = f.read()
            
            # Basic syntax check
            compile(content, 'wxpath/async_core.py', 'exec')
            print("✅ async_core.py syntax is valid")
            
            # Count some key functions
            async_functions = content.count('async def')
            print(f"✅ Found {async_functions} async functions in async_core.py")
            
        except Exception as e:
            print(f"❌ Error checking async_core.py: {e}")

except Exception as e:
    print(f"❌ Unexpected error: {e}")
    import traceback
    traceback.print_exc()