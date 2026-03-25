"""
Core provider interfaces for Mission Control voice orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(slots=True)
class AgentReply:
    """
    Agent provider response payload.

    Args:
        text: Final assistant text reply.
        ok: Whether the provider call succeeded.
        error: Optional error description when ``ok`` is False.

    Returns:
        AgentReply: Structured reply object for orchestration flows.

    Example:
        AgentReply(text="Hello", ok=True, error=None)
    """

    text: str
    ok: bool
    error: str | None = None


@dataclass(slots=True)
class TTSResult:
    """
    TTS provider result payload.

    Args:
        ok: Whether speech synthesis completed successfully.
        file_path: Output file path when ``ok`` is True.
        error: Optional synthesis error message.

    Returns:
        TTSResult: Structured file generation result.

    Example:
        TTSResult(ok=True, file_path=Path("/tmp/reply.mp3"), error=None)
    """

    ok: bool
    file_path: Path | None
    error: str | None = None


class AgentProvider(Protocol):
    """
    Contract for text inference providers.

    Args:
        message: Input utterance to send to an assistant backend.

    Returns:
        AgentReply: Structured inference response.

    Example:
        reply = provider.ask("Summarize priorities for today")
    """

    def ask(self, message: str) -> AgentReply:
        raise NotImplementedError


class TTSProvider(Protocol):
    """
    Contract for text-to-speech providers.

    Args:
        text: Reply text to synthesize.
        output_path: Absolute destination path for the generated audio file.

    Returns:
        TTSResult: Structured synthesis result.

    Example:
        result = provider.synthesize("Hello", Path("/tmp/hello.mp3"))
    """

    def synthesize(self, text: str, output_path: Path) -> TTSResult:
        raise NotImplementedError


class STTProvider(Protocol):
    """
    Contract placeholder for optional speech-to-text providers.

    Args:
        audio_path: Input audio file path.

    Returns:
        str: Transcribed text.

    Example:
        text = provider.transcribe(Path("/tmp/audio.wav"))
    """

    def transcribe(self, audio_path: Path) -> str:
        raise NotImplementedError
