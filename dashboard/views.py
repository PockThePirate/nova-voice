from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.conf import settings

import asyncio
import uuid
import os
import subprocess

import edge_tts

from .models import Agent, NodeStatus, Mission, Event


@login_required
def dashboard_view(request):
    agents = Agent.objects.all()
    voice_agents = agents.filter(kind=Agent.VOICE)
    nodes = NodeStatus.objects.all()
    missions = Mission.objects.order_by("-updated_at")[:10]
    events = Event.objects.all()[:20]

    context = {
        "agents": agents,
        "voice_agents": voice_agents,
        "nodes": nodes,
        "missions": missions,
        "events": events,
    }
    return render(request, "dashboard/dashboard.html", context)


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
            # On error, fall back to a simple echo so the UX still works.
            reply_text = clean
    except Exception:
        reply_text = clean

    # Synthesize reply with Edge TTS (Natasha) to an mp3 file under static/nova_audio
    out_dir = getattr(settings, "NOVA_AUDIO_DIR", settings.BASE_DIR / "static" / "nova_audio")
    os.makedirs(out_dir, exist_ok=True)
    filename = f"{uuid.uuid4()}.mp3"
    out_path = out_dir / filename

    async def synth(text, path):
        communicate = edge_tts.Communicate(text, "en-US-JennyNeural")
        await communicate.save(str(path))

    try:
        asyncio.run(synth(reply_text, out_path))
    except RuntimeError:
        # If an event loop is already running, fall back to create_task pattern
        loop = asyncio.get_event_loop()
        loop.run_until_complete(synth(reply_text, out_path))

    audio_url = f"/static/nova_audio/{filename}"

    return JsonResponse({"reply_text": reply_text, "audio_url": audio_url})
