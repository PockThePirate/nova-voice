from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.http import JsonResponse, FileResponse, Http404
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

import logging
import os
import re
from pathlib import Path

from .models import Agent, NodeStatus, Mission, Event
from .services import (
    EdgeTTSProvider,
    OpenClawCLIProvider,
    ProviderRuntimeConfig,
    VoiceOrchestrator,
)

logger = logging.getLogger("nova")


_NOVA_AUDIO_FILENAME = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\.mp3$"
)


def _nova_audio_output_url_prefix() -> str:
    """
    Public URL prefix for JSON ``audio_url`` (streamed by ``nova_audio_file``).

    Always ``/api/nova/audio/`` unless ``NOVA_AUDIO_LEGACY_STATIC_URL=1`` is set.

    Args:
        None

    Returns:
        str: Path prefix ending with a slash.

    Example:
        orchestrator = VoiceOrchestrator(..., output_url_prefix=_nova_audio_output_url_prefix())
    """
    if os.environ.get("NOVA_AUDIO_LEGACY_STATIC_URL", "").strip() == "1":
        prefix = getattr(settings, "NOVA_AUDIO_URL_PREFIX", "").strip()
        if prefix:
            return prefix if prefix.endswith("/") else prefix + "/"
        return f"{settings.STATIC_URL.rstrip('/')}/nova_audio/"
    return "/api/nova/audio/"


@login_required
def nova_audio_file(request, filename: str):
    """
    Stream a generated Nova TTS MP3 from ``NOVA_AUDIO_DIR`` (same-origin, session auth).

    Args:
        request: HttpRequest (must be authenticated).
        filename: UUID-based ``.mp3`` name only.

    Returns:
        FileResponse: ``audio/mpeg`` stream or HTTP 404.

    Example:
        GET /api/nova/audio/550e8400-e29b-41d4-a716-446655440000.mp3
    """
    if not _NOVA_AUDIO_FILENAME.match(filename):
        raise Http404("Invalid audio file name")
    base = Path(getattr(settings, "NOVA_AUDIO_DIR", settings.BASE_DIR / "static" / "nova_audio")).resolve()
    target = (base / filename).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise Http404("Invalid path") from None
    if not target.is_file():
        raise Http404("Audio not found")
    fh = target.open("rb")
    resp = FileResponse(fh, content_type="audio/mpeg")
    resp["Cache-Control"] = "private, max-age=300"
    return resp


def _record_event(level: str, source: str, message: str) -> None:
    """
    Persist one timeline event without breaking request flow.

    Args:
        level: Event severity (`info`, `warn`, or `error`).
        source: Event producer name.
        message: Human-readable event text.

    Returns:
        None

    Example:
        _record_event(level="info", source="voice_api", message="Request accepted")
    """
    try:
        Event.objects.create(level=level, source=source, message=message)
    except Exception:
        logger.exception("Failed to persist Event")


def _run_voice_orchestration(text: str, source: str) -> tuple[dict, int]:
    """
    Execute the Nova voice orchestration pipeline and return API payload/status.

    Args:
        text: Input text to send to Nova.
        source: Source label for timeline events.

    Returns:
        tuple[dict, int]: JSON payload and HTTP status code.

    Example:
        payload, status = _run_voice_orchestration("status update", "voice_api")
    """
    _record_event(level="info", source=source, message="Nova voice request received")
    orchestrator = VoiceOrchestrator(
        agent_provider=OpenClawCLIProvider(agent_name="nova", timeout_seconds=60),
        tts_provider=EdgeTTSProvider(voice_name="en-US-AriaNeural"),
        output_dir=getattr(settings, "NOVA_AUDIO_DIR", settings.BASE_DIR / "static" / "nova_audio"),
        output_url_prefix=_nova_audio_output_url_prefix(),
    )
    result = orchestrator.run(raw_text=text)
    if not result.ok:
        _record_event(
            level="error",
            source=source,
            message=f"Nova voice request failed with error={result.error or 'unknown'}",
        )
        return {"error": result.error or "voice_failed"}, 500
    _record_event(level="info", source=source, message="Nova voice reply generated")
    return {"reply_text": result.reply_text, "audio_url": result.audio_url}, 200


@login_required
def dashboard_view(request):
    runtime_config = ProviderRuntimeConfig.from_settings()
    agents = Agent.objects.all()
    voice_agents = agents.filter(kind=Agent.VOICE)
    nodes = NodeStatus.objects.all()
    missions = Mission.objects.order_by("-updated_at")[:10]
    events = Event.objects.all()[:20]

    # File-based mission logs under BASE_DIR/missions
    mission_files = []
    missions_dir = Path(settings.BASE_DIR) / "missions"
    if missions_dir.exists():
        for entry in sorted(missions_dir.glob("*.md")):
            slug = entry.stem
            title = slug.replace("_", " ").title()
            mission_files.append({"slug": slug, "title": title})

    # Simple "Today's Focus" from first mission file, if present
    focus_mission = None
    focus_actions = []
    focus_summary_text = ""
    if mission_files:
        first = mission_files[0]
        focus_mission = first
        mission_path = missions_dir / f"{first['slug']}.md"
        try:
            with mission_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
            in_actions = False
            for line in lines:
                stripped = line.strip()
                if stripped.lower().startswith("## next 3 actions"):
                    in_actions = True
                    continue
                if in_actions:
                    if stripped.startswith("## "):
                        break
                    if not stripped:
                        continue
                    # Match: "- text", "* text", "1. text", "2. text", etc.
                    if stripped.startswith("-"):
                        text = stripped[1:].strip()
                    elif stripped.startswith("*"):
                        text = stripped[1:].strip()
                    else:
                        # Check for numbered items like "1.", "2.", etc.
                        parts = stripped.split(".", 1)
                        if len(parts) == 2 and parts[0].strip().isdigit():
                            text = parts[1].strip()
                        else:
                            text = stripped
                    if text:
                        focus_actions.append(text)
            if focus_mission and focus_actions:
                parts = [
                    f"Today's focus mission is {focus_mission['title']}.",
                    "Here are your next actions:",
                ]
                for idx, a in enumerate(focus_actions, start=1):
                    parts.append(f"{idx}. {a}.")
                # Build a prompt for the Nova agent to craft an insightful summary
                actions_list = "; ".join([f"{idx}. {a}" for idx, a in enumerate(focus_actions, start=1)])
                focus_summary_text = (
                    f"Today's focus mission is {focus_mission['title']}. "
                    f"Here are the next actions: {actions_list}. "
                    f"Please provide a brief, insightful overview of these priorities for today."
                )
        except Exception:
            focus_actions = []
            focus_summary_text = ""

    context = {
        "agents": agents,
        "voice_agents": voice_agents,
        "nodes": nodes,
        "missions": missions,
        "events": events,
        "mission_files": mission_files,
        "focus_mission": focus_mission,
        "focus_actions": focus_actions,
        "focus_summary_text": focus_summary_text,
        "provider_capabilities": runtime_config.capabilities,
    }
    return render(request, "dashboard/dashboard.html", context)


@login_required
def missions_list(request):
    base_dir = Path(settings.BASE_DIR)
    missions_index = base_dir / "MISSIONS.md"
    missions_dir = base_dir / "missions"

    missions = []
    if missions_dir.exists():
        for entry in sorted(missions_dir.glob("*.md")):
            slug = entry.stem
            title = slug.replace("_", " ").title()
            missions.append({"slug": slug, "title": title})

    context = {
        "missions": missions,
    }
    return render(request, "dashboard/missions_list.html", context)


@login_required
def mission_detail(request, slug: str):
    base_dir = Path(settings.BASE_DIR)
    mission_path = base_dir / "missions" / f"{slug}.md"
    if not mission_path.exists():
        raise Http404("Mission not found")

    with mission_path.open("r", encoding="utf-8") as f:
        content = f.read()

    context = {
        "slug": slug,
        "content": content,
    }
    return render(request, "dashboard/mission_detail.html", context)


@login_required
def mission_download(request, slug: str):
    base_dir = Path(settings.BASE_DIR)
    mission_path = base_dir / "missions" / f"{slug}.md"
    if not mission_path.exists():
        raise Http404("Mission not found")

    return FileResponse(
        open(mission_path, "rb"),
        as_attachment=True,
        filename=f"{slug}.md",
        content_type="text/markdown",
    )


@login_required
def nova_ws_info(request):
    """
    JSON helper for debugging Nova mic WebSocket URL and gateway import status.

    Args:
        request: HttpRequest (must be authenticated).

    Returns:
        JsonResponse: websocket_url, path, gateway_module_loaded, hint.

    Example:
        GET /api/nova/ws-info/ returns the wss URL the dashboard uses and whether ASGI loaded FastAPI.
    """
    scheme = "wss" if request.is_secure() else "ws"
    host = request.get_host()
    path = "/ws/audio/nova"
    websocket_url = f"{scheme}://{host}{path}"
    custom = getattr(settings, "NOVA_WS_URL", None)
    if custom:
        websocket_url = custom
    gateway_ok = False
    try:
        from mission_control import asgi as asgi_mod

        gateway_ok = getattr(asgi_mod, "nova_gateway_app", None) is not None
    except Exception:
        pass
    return JsonResponse(
        {
            "websocket_url": websocket_url,
            "path": path,
            "gateway_module_loaded": gateway_ok,
            "http_served_by_note": (
                "This JSON is plain HTTP. The mic uses WSS; nginx must forward Upgrade to "
                "uvicorn (mission_control.asgi), not gunicorn WSGI alone."
            ),
            "hint": "DevTools: Network, WS filter, Preserve log, click Wake Nova.",
            "server_check_command": "python manage.py nova_check_deploy --port 8001",
            "deploy_doc": "deploy/CHECKLIST-NOVA-WSS.txt",
        }
    )


@login_required
@require_POST
def toggle_agent_active(request, agent_id: int):
    agent = get_object_or_404(Agent, id=agent_id)
    agent.active = not agent.active
    # If you later wire this to OpenClaw, this is where you'd send a command
    # to start/stop the underlying node/voice runtime.
    agent.save(update_fields=["active"])
    return redirect("dashboard")


@login_required
@require_POST
def set_agent_mode(request, agent_id: int):
    agent = get_object_or_404(Agent, id=agent_id)
    mode = request.POST.get("mode", "").strip()
    agent.mode = mode
    agent.save(update_fields=["mode"])
    return redirect("dashboard")


@login_required
@require_POST
def nova_voice_api(request):
    text = request.POST.get("text", "").strip()
    if not text:
        return JsonResponse({"error": "text required"}, status=400)
    payload, status = _run_voice_orchestration(text=text, source="voice_api")
    return JsonResponse(payload, status=status)


@csrf_exempt
@require_POST
def nova_voice_gateway_api(request):
    """
    Internal endpoint for gateway STT call-through without browser CSRF/session requirements.

    Args:
        request: HttpRequest containing transcript text and optional gateway token header.

    Returns:
        JsonResponse: Same schema as `nova_voice_api`.

    Example:
        POST /api/nova/voice/internal/ with form field `text`.
    """
    expected_token = getattr(settings, "NOVA_GATEWAY_INTERNAL_TOKEN", "").strip()
    provided_token = request.headers.get("X-Nova-Gateway-Token", "").strip()
    if expected_token and provided_token != expected_token:
        return JsonResponse({"error": "forbidden"}, status=403)
    text = request.POST.get("text", "").strip()
    if not text:
        return JsonResponse({"error": "text required"}, status=400)
    payload, status = _run_voice_orchestration(text=text, source="voice_gateway_api")
    return JsonResponse(payload, status=status)
