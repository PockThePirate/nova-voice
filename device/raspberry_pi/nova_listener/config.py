"""Configuration for the headless Nova listener."""

from __future__ import annotations

import os
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ListenerConfig:
    """
    General purpose: Hold runtime settings for the Raspberry Pi listener service.

    Args:
        base_url (str): Base mission-control URL (for example, ``https://novamission.cloud``).
        gateway_token (str): Shared machine token sent in ``X-Nova-Gateway-Token``.
        vosk_model_path (str): Local filesystem path to extracted Vosk model.
        sample_rate (int): Microphone sample rate expected by Vosk.
        wake_timeout_s (float): Seconds to wait for command silence after wake.
        max_command_s (float): Hard cap for one command capture window.
        wake_phrases (tuple[str, ...]): Phrases that start command capture.
        audio_player_cmd (str): Playback command with one ``{path}`` placeholder.

    Returns:
        ListenerConfig: Immutable config object used by service classes.

    Example:
        cfg = ListenerConfig.from_env()
    """

    base_url: str
    gateway_token: str
    vosk_model_path: str
    sample_rate: int
    wake_timeout_s: float
    max_command_s: float
    wake_phrases: tuple[str, ...]
    audio_player_cmd: str

    @classmethod
    def from_env(cls) -> "ListenerConfig":
        """
        General purpose: Build runtime config from environment variables.

        Args:
            None

        Returns:
            ListenerConfig: Parsed config with defaults for headless Raspberry Pi.

        Example:
            cfg = ListenerConfig.from_env()
        """
        wake_csv = os.environ.get("NOVA_WAKE_PHRASES", "nova,hey nova")
        wake_phrases = tuple(x.strip().lower() for x in wake_csv.split(",") if x.strip())
        if not wake_phrases:
            wake_phrases = ("nova", "hey nova")
        return cls(
            base_url=os.environ.get("NOVA_BASE_URL", "").strip().rstrip("/"),
            gateway_token=os.environ.get("NOVA_GATEWAY_INTERNAL_TOKEN", "").strip(),
            vosk_model_path=os.environ.get("NOVA_VOSK_MODEL_PATH", "").strip(),
            sample_rate=int(os.environ.get("NOVA_VOSK_SAMPLE_RATE", "16000")),
            wake_timeout_s=float(os.environ.get("NOVA_COMMAND_SILENCE_SECONDS", "3.75")),
            max_command_s=float(os.environ.get("NOVA_MAX_COMMAND_SECONDS", "30")),
            wake_phrases=wake_phrases,
            audio_player_cmd=os.environ.get("NOVA_AUDIO_PLAYER_CMD", "mpg123 -q {path}").strip(),
        )

    def validate(self) -> None:
        """
        General purpose: Validate mandatory settings before listener startup.

        Args:
            None

        Returns:
            None

        Example:
            cfg.validate()
        """
        if not self.base_url:
            raise ValueError("NOVA_BASE_URL is required")
        if not self.base_url.startswith("https://"):
            raise ValueError("NOVA_BASE_URL must use https://")
        if not self.gateway_token:
            raise ValueError("NOVA_GATEWAY_INTERNAL_TOKEN is required")
        if not self.vosk_model_path:
            raise ValueError("NOVA_VOSK_MODEL_PATH is required")
        model_dir = Path(self.vosk_model_path)
        if not model_dir.is_dir():
            raise ValueError("NOVA_VOSK_MODEL_PATH directory not found")
        model_files = ("am", "conf", "graph", "ivector")
        for name in model_files:
            if not (model_dir / name).exists():
                raise ValueError(f"NOVA_VOSK_MODEL_PATH missing required entry: {name}")
        player_tokens = shlex.split(self.audio_player_cmd)
        if not player_tokens:
            raise ValueError("NOVA_AUDIO_PLAYER_CMD is required")
        player_bin = player_tokens[0]
        if shutil.which(player_bin) is None:
            raise ValueError(f"NOVA_AUDIO_PLAYER_CMD binary not found: {player_bin}")

