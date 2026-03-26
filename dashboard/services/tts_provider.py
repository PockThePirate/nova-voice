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
        import threading
        
        result_container = {"exception": None, "done": False}
        
        def run_async():
            try:
                # Create a new event loop for this thread
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    new_loop.run_until_complete(self._synthesize_async(text, output_path))
                    result_container["done"] = True
                finally:
                    new_loop.close()
            except Exception as e:
                result_container["exception"] = e
        
        # Run TTS in a separate thread to avoid event loop conflicts
        thread = threading.Thread(target=run_async)
        thread.start()
        thread.join()
        
        if result_container["exception"]:
            self.logger.exception("Edge TTS synth failed", exc_info=result_container["exception"])
            return TTSResult(ok=False, file_path=None, error="tts_failed")
        elif result_container["done"]:
            return TTSResult(ok=True, file_path=output_path, error=None)
        else:
            return TTSResult(ok=False, file_path=None, error="tts_failed")
