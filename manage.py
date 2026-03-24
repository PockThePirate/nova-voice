#!/usr/bin/env python3
"""Minimal manage.py for Nova Mission Control"""
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mission_control.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Make sure Django is installed in your environment."
        ) from exc
    execute_from_command_line(sys.argv)
