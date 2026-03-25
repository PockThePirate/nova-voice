"""
Provider capability descriptors aligned with OpenClaw plugin concepts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ProviderCapabilities:
    """
    Describe optional provider capabilities for feature toggles.

    Args:
        text_inference: Supports text inference requests.
        speech_synthesis: Supports text-to-speech generation.
        media_understanding: Supports image/audio understanding.
        web_search: Supports web search features.

    Returns:
        ProviderCapabilities: Capability flags for runtime checks.

    Example:
        caps = ProviderCapabilities(text_inference=True, speech_synthesis=True)
    """

    text_inference: bool = True
    speech_synthesis: bool = True
    media_understanding: bool = False
    web_search: bool = False


DEFAULT_CAPABILITIES = ProviderCapabilities()
