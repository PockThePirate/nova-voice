"""Headless microphone listener for wake + command recognition."""

from __future__ import annotations

import queue
import shlex
import subprocess
import time
from pathlib import Path

import sounddevice as sd
from vosk import KaldiRecognizer, Model

from .client import NovaApiClient
from .config import ListenerConfig


class HeadlessNovaListener:
    """
    General purpose: Run always-on wake listening and command relay with local playback.

    Args:
        config (ListenerConfig): Runtime settings from env file.
        client (NovaApiClient): HTTP client for mission-control APIs.

    Returns:
        HeadlessNovaListener: Stateful runner used by the systemd service.

    Example:
        listener = HeadlessNovaListener(cfg, client)
    """

    def __init__(self, config: ListenerConfig, client: NovaApiClient) -> None:
        self.config = config
        self.client = client
        self._model = Model(config.vosk_model_path)
        self._wake_recognizer = KaldiRecognizer(self._model, float(config.sample_rate))
        self._audio_queue: "queue.Queue[bytes]" = queue.Queue(maxsize=100)

    def run_forever(self) -> None:
        """
        General purpose: Start microphone stream and keep processing wake/command loops.

        Args:
            None

        Returns:
            None

        Example:
            listener.run_forever()
        """
        with sd.RawInputStream(
            samplerate=self.config.sample_rate,
            blocksize=8000,
            dtype="int16",
            channels=1,
            callback=self._on_audio_chunk,
        ):
            while True:
                audio_bytes = self._audio_queue.get()
                if self._wake_recognizer.AcceptWaveform(audio_bytes):
                    text = self._extract_text(self._wake_recognizer.Result())
                else:
                    text = self._extract_text(self._wake_recognizer.PartialResult())
                wake_phrase = self._detect_wake_phrase(text)
                if not wake_phrase:
                    continue
                command = self._capture_command_after_wake(wake_phrase)
                if not command:
                    continue
                self._handle_command(command)

    def _on_audio_chunk(self, indata: bytes, frames: int, time_info: dict, status: sd.CallbackFlags) -> None:
        """
        General purpose: Queue microphone bytes from sounddevice callback thread.

        Args:
            indata (bytes): Raw PCM audio bytes from microphone.
            frames (int): Frame count in this callback (unused).
            time_info (dict): Timing information from sounddevice (unused).
            status (sd.CallbackFlags): Callback status flags.

        Returns:
            None

        Example:
            self._on_audio_chunk(indata, frames, time_info, status)
        """
        _ = (frames, time_info)
        if status:
            return
        try:
            self._audio_queue.put_nowait(bytes(indata))
        except queue.Full:
            pass

    def _detect_wake_phrase(self, text: str) -> str:
        """
        General purpose: Match configured wake phrases in recognizer text.

        Args:
            text (str): Recognized partial or final text.

        Returns:
            str: Matched wake phrase, or empty string when no match.

        Example:
            phrase = self._detect_wake_phrase("hey nova what time is it")
        """
        low = (text or "").strip().lower()
        if not low:
            return ""
        for phrase in self.config.wake_phrases:
            if phrase in low:
                return phrase
        return ""

    def _capture_command_after_wake(self, wake_phrase: str) -> str:
        """
        General purpose: Capture command text after a detected wake phrase.

        Args:
            wake_phrase (str): Phrase that triggered wake mode.

        Returns:
            str: Command text without wake phrase, or empty when timed out.

        Example:
            cmd = self._capture_command_after_wake("nova")
        """
        recognizer = KaldiRecognizer(self._model, float(self.config.sample_rate))
        capture_started = time.monotonic()
        last_text_change = capture_started
        last_command = ""

        while True:
            now = time.monotonic()
            if now - capture_started >= self.config.max_command_s:
                break
            if last_command and now - last_text_change >= self.config.wake_timeout_s:
                break
            audio_bytes = self._audio_queue.get()
            if recognizer.AcceptWaveform(audio_bytes):
                text = self._extract_text(recognizer.Result())
            else:
                text = self._extract_text(recognizer.PartialResult())
            command = self._strip_wake_phrase(text, wake_phrase)
            if command and command != last_command:
                last_command = command
                last_text_change = time.monotonic()
        return last_command.strip()

    def _strip_wake_phrase(self, text: str, wake_phrase: str) -> str:
        """
        General purpose: Remove wake phrase prefix from recognized text.

        Args:
            text (str): Candidate transcript including wake phrase.
            wake_phrase (str): Phrase used to trigger command capture.

        Returns:
            str: Cleaned command text after wake phrase.

        Example:
            cmd = self._strip_wake_phrase("hey nova what is weather", "hey nova")
        """
        low = (text or "").strip().lower()
        if not low:
            return ""
        idx = low.rfind(wake_phrase.lower())
        if idx == -1:
            return low
        return low[idx + len(wake_phrase) :].strip()

    def _extract_text(self, result_json: str) -> str:
        """
        General purpose: Extract ``text`` or ``partial`` value from Vosk JSON payload.

        Args:
            result_json (str): JSON text from ``Result()`` or ``PartialResult()``.

        Returns:
            str: Extracted transcript chunk.

        Example:
            text = self._extract_text(recognizer.PartialResult())
        """
        # Keep this lightweight to avoid extra deps.
        token = '"partial"'
        if '"text"' in result_json:
            token = '"text"'
        marker = result_json.find(token)
        if marker < 0:
            return ""
        colon = result_json.find(":", marker)
        if colon < 0:
            return ""
        first_quote = result_json.find('"', colon + 1)
        if first_quote < 0:
            return ""
        second_quote = result_json.find('"', first_quote + 1)
        if second_quote < 0:
            return ""
        return result_json[first_quote + 1 : second_quote].strip()

    def _handle_command(self, command: str) -> None:
        """
        General purpose: Send command to Nova and play returned audio reply.

        Args:
            command (str): Final command text from wake capture.

        Returns:
            None

        Example:
            self._handle_command("read my task list")
        """
        try:
            payload = self.client.send_text(command)
            audio_url = str(payload.get("audio_url", "")).strip()
            if not audio_url:
                return
            tmp_audio = self.client.fetch_audio_to_temp(audio_url)
            self._play_audio(tmp_audio)
        except Exception:
            # Keep listener alive; systemd handles crash loops, but this avoids churn.
            return

    def _play_audio(self, audio_path: Path) -> None:
        """
        General purpose: Play MP3 reply through configured player command.

        Args:
            audio_path (Path): Local MP3 file to play.

        Returns:
            None

        Example:
            self._play_audio(Path("/tmp/nova-reply.mp3"))
        """
        command = self.config.audio_player_cmd.format(path=str(audio_path))
        try:
            subprocess.run(shlex.split(command), check=False)
        finally:
            audio_path.unlink(missing_ok=True)

