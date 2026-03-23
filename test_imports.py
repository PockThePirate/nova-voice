#!/usr/bin/env python3
"""
Test script to verify all imports work on Android.
Run this manually if app crashes.
"""

import sys
print("Python version:", sys.version)

tests = [
    ("kivy", lambda: __import__("kivy")),
    ("kivymd", lambda: __import__("kivymd")),
    ("websockets", lambda: __import__("websockets")),
    ("jnius", lambda: __import__("jnius")),
    ("vosk", lambda: __import__("vosk")),
    ("nacl", lambda: __import__("nacl")),
]

for name, test in tests:
    try:
        test()
        print(f"✓ {name} imported successfully")
    except ImportError as e:
        print(f"✗ {name} FAILED: {e}")
    except Exception as e:
        print(f"✗ {name} ERROR: {type(e).__name__}: {e}")

print("\nAll tests complete")