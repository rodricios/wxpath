#!/usr/bin/env python3
"""
Test import of regular wxpath functionality to ensure base system works.
"""

try:
    from wxpath.core import wxpath, evaluate_wxpath_bfs_iter
    print("✅ Successfully imported sync wxpath functions")
    
    # Test basic functionality with a string
    results = list(evaluate_wxpath_bfs_iter(None, [('xpath', '//text()')], max_depth=1))
    print(f"✅ Basic function call works, got {len(results)} results")
    
except Exception as e:
    print(f"❌ Error importing or testing sync functions: {e}")
    import traceback
    traceback.print_exc()

# Test if the current working directory has the project
import os
print(f"Current directory: {os.getcwd()}")
print(f"Files in current directory: {os.listdir('.')}")

if 'wxpath' in os.listdir('.'):
    print("✅ wxpath directory found")
    print(f"Files in wxpath/: {os.listdir('wxpath')}")
else:
    print("❌ wxpath directory not found")