"""
Template context processors for Mission Control.

Example (settings): add "dashboard.context_processors.nova_ws_url" to TEMPLATES OPTIONS.
"""

from django.conf import settings


def nova_ws_url(request):
    """
    Expose optional full WebSocket URL for Nova streaming (split-host deployments).

    Args:
        request: Django HttpRequest (unused; kept for context processor signature).

    Returns:
        dict: ``{"nova_ws_url": str|None}`` from ``settings.NOVA_WS_URL``.

    Example:
        In template: {% if nova_ws_url %}data-nova-ws-url="{{ nova_ws_url }}"{% endif %}
    """
    url = getattr(settings, "NOVA_WS_URL", None)
    return {"nova_ws_url": url}
