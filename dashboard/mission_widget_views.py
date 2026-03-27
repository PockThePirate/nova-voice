"""
POST handlers for mission dashboard widgets (build block, pipeline, IoT lab).
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import DailyBuildBlock, Event, IoTLabEntry, PipelineItem

logger = logging.getLogger("nova")


def _append_timeline_event(level: str, source: str, message: str) -> None:
    """
    Persist a dashboard timeline row without breaking the request.

    Args:
        level (str): One of ``info``, ``warn``, ``error``.
        source (str): Short producer label (e.g. ``build_block``).
        message (str): Human-readable text.

    Returns:
        None

    Example:
        _append_timeline_event("info", "iot", "Touched sensor node")
    """
    try:
        Event.objects.create(level=level, source=source, message=message)
    except Exception:
        logger.exception("Failed to persist mission timeline Event")


@login_required
@require_POST
def dashboard_build_toggle(request):
    """
    Toggle today's ``DailyBuildBlock.done`` flag (creates a default row if missing).

    Args:
        request: Authenticated POST request (CSRF required by middleware).

    Returns:
        HttpResponseRedirect: Back to dashboard.

    Example:
        POST /mission/build/toggle/ with CSRF token.
    """
    today = timezone.localdate()
    block, _ = DailyBuildBlock.objects.get_or_create(
        date=today,
        defaults={
            "title": "Today's build block",
            "done": False,
            "notes": "",
        },
    )
    block.done = not block.done
    block.save(update_fields=["done"])
    _append_timeline_event(
        "info",
        "build_block",
        f"Build block {'marked done' if block.done else 'reopened'}: {block.title}",
    )
    return redirect("dashboard")


@login_required
@require_POST
def dashboard_pipeline_next(request, pipeline_id: int):
    """
    Update ``next_action`` on a pipeline row from form field ``next_action``.

    Args:
        request: Authenticated POST request.
        pipeline_id (int): Primary key of ``PipelineItem``.

    Returns:
        HttpResponseRedirect: Back to dashboard.

    Example:
        POST /mission/pipeline/3/next/ with ``next_action=Follow up email``.
    """
    item = get_object_or_404(PipelineItem, pk=pipeline_id)
    text = (request.POST.get("next_action") or "").strip()[:500]
    if text:
        item.next_action = text
        item.save(update_fields=["next_action", "updated_at"])
        _append_timeline_event(
            "info",
            "income",
            f"Pipeline next action set for {item.name}: {text}",
        )
    return redirect("dashboard")


@login_required
@require_POST
def dashboard_iot_touch(request, entry_id: int):
    """
    Bump ``last_touched`` on an IoT lab entry (full save for auto_now field).

    Args:
        request: Authenticated POST request.
        entry_id (int): Primary key of ``IoTLabEntry``.

    Returns:
        HttpResponseRedirect: Back to dashboard.

    Example:
        POST /mission/iot/5/touch/
    """
    entry = get_object_or_404(IoTLabEntry, pk=entry_id)
    entry.save()
    _append_timeline_event(
        "info",
        "iot",
        f"IoT lab touched: {entry.name}",
    )
    return redirect("dashboard")
