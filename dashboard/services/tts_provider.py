"""
Edge TTS-backed speech synthesis provider.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import edge_tts

from .interfaces import TTSProvider, TTSResult


class EdgeTTSProvider(TTSProvider):
    """
    Synthesize text to mp3 files using Edge TTS.

    Args:
        voice_name: Voice identifier understood by edge-tts.

    Returns:
        EdgeTTSProvider: Configured provider instance.

    Example:
        provider = EdgeTTSProvider(voice_name="en-US-AriaNeural")
    """

    def __init__(self, voice_name: str = "en-US-AriaNeural") -> None:
        self.voice_name = voice_name
        self.logger = logging.getLogger("nova")

    async def _synthesize_async(self, text: str, output_path: Path) -> None:
        """
        Perform asynchronous Edge TTS synthesis.

        Args:
            text: Text to synthesize.
            output_path: Destination path for mp3 output.

        Returns:
            None

        Example:
            await provider._synthesize_async("Hello", Path("/tmp/hello.mp3"))
        """
        communicate = edge_tts.Communicate(text, self.voice_name)
        await communicate.save(str(output_path))

    def synthesize(self, text: str, output_path: Path) -> TTSResult:
        """
        Generate speech audio and save it to disk.

        Args:
            text: Text to synthesize into speech.
            output_path: Absolute file path for mp3 output.

        Returns:
            TTSResult: Synthesis outcome and file path.

        Example:
            result = provider.synthesize("Hello", Path("/tmp/hello.mp3"))
        """
        try:
            asyncio.run(self._synthesize_async(text, output_path))
            return TTSResult(ok=True, file_path=output_path, error=None)
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self._synthesize_async(text, output_path))
                return TTSResult(ok=True, file_path=output_path, error=None)
            except Exception:
                self.logger.exception("Edge TTS synth failed (runtime loop fallback)")
                return TTSResult(ok=False, file_path=None, error="tts_failed")
        except Exception:
            self.logger.exception("Edge TTS synth failed")
            return TTSResult(ok=False, file_path=None, error="tts_failed")
