"""HTTP client for Nova internal machine endpoints."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import requests


class NovaApiClient:
    """
    General purpose: Post transcripts and fetch audio for headless Nova playback.

    Args:
        base_url (str): Mission control base URL without trailing slash.
        gateway_token (str): Shared token sent in ``X-Nova-Gateway-Token``.
        timeout_seconds (float): Request timeout for each HTTP call.

    Returns:
        NovaApiClient: Ready-to-use API client for voice/internal endpoints.

    Example:
        client = NovaApiClient("https://novamission.cloud", "secret-token")
    """

    def __init__(self, base_url: str, gateway_token: str, timeout_seconds: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._session = requests.Session()
        self._session.headers.update({"X-Nova-Gateway-Token": gateway_token})
        self._audio_id_regex = re.compile(
            r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\.mp3)"
        )

    def send_text(self, text: str) -> dict:
        """
        General purpose: Send recognized speech to the Nova internal voice endpoint.

        Args:
            text (str): Recognized command text to execute.

        Returns:
            dict: Parsed JSON payload containing ``reply_text`` and ``audio_url``.

        Example:
            payload = client.send_text("what is on my schedule")
        """
        url = f"{self.base_url}/api/nova/voice/internal/"
        response = self._session.post(url, data={"text": text}, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("nova_voice_internal_invalid_json")
        return payload

    def fetch_audio_to_temp(self, audio_url: str) -> Path:
        """
        General purpose: Download reply MP3 through device-auth endpoint to temp file.

        Args:
            audio_url (str): ``audio_url`` from Nova JSON response.

        Returns:
            Path: Path to temporary MP3 file ready for playback.

        Example:
            mp3_path = client.fetch_audio_to_temp("/api/nova/audio/uuid.mp3")
        """
        filename = self._extract_audio_filename(audio_url)
        url = f"{self.base_url}/api/nova/audio/device/{filename}"
        response = self._session.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        fd, path_str = tempfile.mkstemp(prefix="nova-reply-", suffix=".mp3")
        path = Path(path_str)
        try:
            with os.fdopen(fd, "wb") as fp:
                fp.write(response.content)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return path

    def _extract_audio_filename(self, audio_url: str) -> str:
        """
        General purpose: Parse UUID mp3 filename from Nova ``audio_url`` field.

        Args:
            audio_url (str): URL or path returned by Nova API.

        Returns:
            str: UUID-style mp3 filename used by device audio endpoint.

        Example:
            name = client._extract_audio_filename("/api/nova/audio/550e...000.mp3")
        """
        match = self._audio_id_regex.search(audio_url or "")
        if not match:
            raise ValueError("nova_audio_filename_missing")
        return match.group(1)

