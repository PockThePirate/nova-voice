"""
Voice orchestration service for Nova text->reply->audio flow.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .interfaces import AgentProvider, TTSProvider


@dataclass(slots=True)
class VoiceResponse:
    """
    Public response payload for `nova_voice_api`.

    Args:
        reply_text: Final text reply to return to the client.
        audio_url: Static URL of generated mp3 file.
        ok: Indicates whether the orchestration completed successfully.
        error: Optional error code when `ok` is False.

    Returns:
        VoiceResponse: API-oriented structured response.

    Example:
        VoiceResponse(reply_text="Hi", audio_url="/static/nova_audio/a.mp3", ok=True, error=None)
    """

    reply_text: str
    audio_url: str | None
    ok: bool
    error: str | None = None


class VoiceOrchestrator:
    """
    Coordinate provider inference and TTS generation for Nova voice API.

    Args:
        agent_provider: Provider implementation for assistant replies.
        tts_provider: Provider implementation for speech synthesis.
        output_dir: Directory where mp3 files are stored.
        output_url_prefix: Public URL prefix mapped to output_dir files.

    Returns:
        VoiceOrchestrator: Ready-to-use orchestrator instance.

    Example:
        orchestrator = VoiceOrchestrator(agent_provider, tts_provider, Path("/tmp"), "/static/nova_audio/")
    """

    def __init__(
        self,
        agent_provider: AgentProvider,
        tts_provider: TTSProvider,
        output_dir: Path,
        output_url_prefix: str,
    ) -> None:
        self.agent_provider = agent_provider
        self.tts_provider = tts_provider
        self.output_dir = output_dir
        self.output_url_prefix = output_url_prefix.rstrip("/") + "/"

    @staticmethod
    def normalize_wake_prefix(text: str) -> str:
        """
        Remove optional wake prefixes from an utterance.

        Args:
            text: Raw user input string.

        Returns:
            str: Cleaned prompt passed to provider.

        Example:
            clean = VoiceOrchestrator.normalize_wake_prefix("Hey Nova summarize logs")
        """
        lowered = text.lower()
        if lowered.startswith("hey nova "):
            return text[len("hey nova ") :].lstrip()
        if lowered.startswith("nova "):
            return text[len("nova ") :].lstrip()
        return text

    def run(self, raw_text: str) -> VoiceResponse:
        """
        Execute one full voice request orchestration.

        Args:
            raw_text: Raw text from request body.

        Returns:
            VoiceResponse: Result containing reply text and optional audio URL.

        Example:
            result = orchestrator.run("Nova what is my mission?")
        """
        clean = self.normalize_wake_prefix(raw_text.strip())
        if not clean:
            return VoiceResponse(reply_text="", audio_url=None, ok=False, error="text_required")

        agent_result = self.agent_provider.ask(clean)
        if not agent_result.ok:
            return VoiceResponse(
                reply_text="",
                audio_url=None,
                ok=False,
                error=agent_result.error or "agent_provider_failed",
            )
        reply_text = agent_result.text.strip() if agent_result.text else ""
        if not reply_text:
            return VoiceResponse(reply_text="", audio_url=None, ok=False, error="empty_agent_reply")

        os.makedirs(self.output_dir, exist_ok=True)
        filename = f"{uuid.uuid4()}.mp3"
        out_path = self.output_dir / filename

        tts_result = self.tts_provider.synthesize(reply_text, out_path)
        if not tts_result.ok:
            return VoiceResponse(reply_text=reply_text, audio_url=None, ok=False, error=tts_result.error)

        self._cleanup_old_audio_files(max_age_seconds=3600)
        audio_url = f"{self.output_url_prefix}{filename}"
        return VoiceResponse(reply_text=reply_text, audio_url=audio_url, ok=True, error=None)

    def _cleanup_old_audio_files(self, max_age_seconds: int) -> None:
        """
        Best-effort cleanup of stale generated audio files.

        Args:
            max_age_seconds: Age threshold in seconds for deletion.

        Returns:
            None

        Example:
            orchestrator._cleanup_old_audio_files(max_age_seconds=3600)
        """
        cutoff = time.time() - max_age_seconds
        for entry in os.scandir(self.output_dir):
            try:
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    os.remove(entry.path)
            except Exception:
                continue
