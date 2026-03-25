"""
Runtime configuration helpers for provider capability toggles.
"""

from __future__ import annotations

from dataclasses import dataclass
from django.conf import settings

from .provider_capabilities import ProviderCapabilities


@dataclass(slots=True)
class ProviderRuntimeConfig:
    """
    Resolve provider runtime toggles from Django settings.

    Args:
        capabilities: Resolved provider capability flags.

    Returns:
        ProviderRuntimeConfig: Runtime configuration object.

    Example:
        config = ProviderRuntimeConfig.from_settings()
    """

    capabilities: ProviderCapabilities

    @classmethod
    def from_settings(cls) -> "ProviderRuntimeConfig":
        """
        Build runtime config from `NOVA_PROVIDER_CAPABILITIES` setting.

        Args:
            None

        Returns:
            ProviderRuntimeConfig: Parsed runtime config with defaults.

        Example:
            config = ProviderRuntimeConfig.from_settings()
        """
        payload = getattr(settings, "NOVA_PROVIDER_CAPABILITIES", {}) or {}
        return cls(
            capabilities=ProviderCapabilities(
                text_inference=bool(payload.get("text_inference", True)),
                speech_synthesis=bool(payload.get("speech_synthesis", True)),
                media_understanding=bool(payload.get("media_understanding", False)),
                web_search=bool(payload.get("web_search", False)),
            )
        )
