"""
ASGI entrypoint: Django (HTTP) plus Nova WebSocket at ``/ws/audio/nova`` in one process.

Use this with uvicorn when nginx proxies **all** site traffic to one upstream and includes
WebSocket ``Upgrade`` headers on that upstream. You then do **not** need a second port or a
separate ``location /ws/audio/nova`` block to a standalone gateway.

If ``nova-audio-gateway`` is not next to ``mission_control`` in the filesystem, set the
environment variable ``NOVA_AUDIO_GATEWAY_ROOT`` to that directory (must contain ``app.py``).

Example:

    cd /path/to/mission_control
    uvicorn mission_control.asgi:application --host 127.0.0.1 --port 8001
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

_logger = logging.getLogger(__name__)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mission_control.settings")

# Default: sibling ``nova-audio-gateway/`` next to the ``mission_control`` project directory.
_ASGI_FILE = Path(__file__).resolve()
_WORKSPACE_ROOT = _ASGI_FILE.parents[2]
_default_gateway = _WORKSPACE_ROOT / "nova-audio-gateway"
_env_gateway = os.environ.get("NOVA_AUDIO_GATEWAY_ROOT", "").strip()
_GATEWAY_DIR = Path(_env_gateway) if _env_gateway else _default_gateway

nova_gateway_app = None
if _GATEWAY_DIR.is_dir():
    gw = str(_GATEWAY_DIR)
    if gw not in sys.path:
        sys.path.insert(0, gw)
    try:
        from app import app as nova_gateway_app  # type: ignore  # noqa: E402
    except Exception as exc:
        _logger.warning("Nova audio gateway not importable: %s", exc)
        nova_gateway_app = None
else:
    _logger.warning("nova-audio-gateway not found at %s", _GATEWAY_DIR)

from django.core.asgi import get_asgi_application  # noqa: E402

django_asgi_app = get_asgi_application()

_NOVA_WS_PATH = "/ws/audio/nova"


async def _reject_nova_ws_missing_gateway(receive, send) -> None:
    """
    Close the socket with an explicit code when FastAPI gateway is not importable.

    Args:
        receive: ASGI receive callable.
        send: ASGI send callable.

    Returns:
        None

    Example:
        Called from ``application`` when path is ``/ws/audio/nova`` but ``nova_gateway_app`` is None.
    """
    reason = "Nova gateway not loaded: pip install -r requirements.txt and run uvicorn ASGI"
    close_msg = {"type": "websocket.close", "code": 4500, "reason": reason}
    try:
        for _ in range(16):
            try:
                message = await asyncio.wait_for(receive(), timeout=20.0)
            except asyncio.TimeoutError:
                await send(close_msg)
                return
            mtype = message.get("type")
            if mtype == "websocket.disconnect":
                return
            if mtype == "websocket.connect":
                await send(close_msg)
                return
        await send(close_msg)
    except Exception:
        try:
            await send(close_msg)
        except Exception:
            pass


async def application(scope, receive, send):
    """
    Dispatch WebSocket connections for Nova audio to the FastAPI app; otherwise Django.

    Args:
        scope: ASGI connection scope dict.
        receive: ASGI event receive callable.
        send: ASGI event send callable.

    Returns:
        None

    Example:
        ``uvicorn mission_control.asgi:application --host 127.0.0.1 --port 8001``
    """
    if scope["type"] == "websocket":
        path = (scope.get("path") or "").rstrip("/") or "/"
        if path == _NOVA_WS_PATH:
            if nova_gateway_app is not None:
                await nova_gateway_app(scope, receive, send)
            else:
                await _reject_nova_ws_missing_gateway(receive, send)
            return
    await django_asgi_app(scope, receive, send)
