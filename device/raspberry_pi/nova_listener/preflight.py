"""Systemd preflight checks for headless Nova listener."""

from __future__ import annotations

import sys

from .config import ListenerConfig


def main() -> int:
    """
    General purpose: Validate listener configuration before systemd ExecStart.

    Args:
        None

    Returns:
        int: ``0`` when preflight checks pass, non-zero otherwise.

    Example:
        raise SystemExit(main())
    """
    try:
        cfg = ListenerConfig.from_env()
        cfg.validate()
    except Exception as exc:
        print(f"[nova-listener] preflight failed: {exc}", file=sys.stderr)
        return 2
    print("[nova-listener] preflight passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

