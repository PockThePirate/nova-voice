from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.http import JsonResponse, FileResponse, Http404
from django.conf import settings

import asyncio
import uuid
import os
import subprocess
import logging
from pathlib import Path

import edge_tts

from .models import Agent, NodeStatus, Mission, Event

logger = logging.getLogger("nova")


@login_required
def dashboard_view(request):
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
                if line.strip().lower().startswith("## next 3 actions"):
                    in_actions = True
                    continue
                if in_actions:
                    if line.strip().startswith("## "):
                        break
                    if line.strip().startswith("-") or line.strip().startswith("*") or any(line.strip().startswith(f"{n}.") for n in range(1, 10)):
                        text = line.strip().lstrip("-*0123456789. ")
                        if text:
                            focus_actions.append(text)
            if focus_mission and focus_actions:
                parts = [
                    f"Today's focus mission is {focus_mission['title']}.",
                    "Here are your next actions:",
                ]
                for idx, a in enumerate(focus_actions, start=1):
                    parts.append(f"{idx}. {a}.")
                focus_summary_text = " " .join(parts)
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

    # Route the utterance to the `nova` agent via the OpenClaw CLI, after
    # stripping an optional wake word ("Nova" / "Hey Nova").
    lowered = text.lower()
    if lowered.startswith("hey nova "):
        clean = text[len("hey nova "):].lstrip()
    elif lowered.startswith("nova "):
        clean = text[len("nova "):].lstrip()
    else:
        clean = text

    reply_text = clean
    try:
        # Use the official CLI to talk to the `nova` agent so we don't have
        # to re‑implement the Gateway protocol here.
        proc = subprocess.run(
            [
                "openclaw",
                "agent",
                "--agent",
                "nova",
                "--message",
                clean,
                "--no-color",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            # Take the last non-empty line from stdout, to strip any
            # preamble / noise and keep just Nova's reply.
            lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
            if lines:
                reply_text = lines[-1]
            else:
                reply_text = clean
        else:
            logger.error(
                "Nova CLI failed",
                extra={
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "returncode": proc.returncode,
                },
            )
            reply_text = clean
    except Exception:
        logger.exception("Nova CLI exception")
        reply_text = clean

    # Synthesize reply with Edge TTS (Natasha) to an mp3 file under static/nova_audio
    out_dir = getattr(settings, "NOVA_AUDIO_DIR", settings.BASE_DIR / "static" / "nova_audio")
    os.makedirs(out_dir, exist_ok=True)
    filename = f"{uuid.uuid4()}.mp3"
    out_path = out_dir / filename

    async def synth(text, path):
        communicate = edge_tts.Communicate(text, "en-US-AriaNeural")
        await communicate.save(str(path))

    try:
        asyncio.run(synth(reply_text, out_path))
    except RuntimeError:
        # If an event loop is already running, fall back to create_task pattern
        loop = asyncio.get_event_loop()
        loop.run_until_complete(synth(reply_text, out_path))
    except Exception:
        logger.exception("Edge TTS synth failed", extra={"reply_text": reply_text})
        return JsonResponse({"error": "tts_failed"}, status=500)

    # Best-effort cleanup: remove audio files older than 1 hour on each request
    try:
      import time
      cutoff = time.time() - 3600
      for entry in os.scandir(out_dir):
          try:
              if entry.is_file() and entry.stat().st_mtime < cutoff:
                  os.remove(entry.path)
          except Exception:
              # Cleanup failures shouldn't break replies
              logger = logging.getLogger("nova")
              logger.exception("Failed to remove old nova audio file")
    except Exception:
      pass

    audio_url = f"/static/nova_audio/{filename}"

    return JsonResponse({"reply_text": reply_text, "audio_url": audio_url})
