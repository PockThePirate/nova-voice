"""
OpenClaw CLI-backed agent provider implementation.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

from .interfaces import AgentProvider, AgentReply


class OpenClawCLIProvider(AgentProvider):
    """
    Execute OpenClaw agent inference via subprocess CLI.

    Args:
        agent_name: OpenClaw agent id to invoke.
        timeout_seconds: Maximum execution time for the CLI process.

    Returns:
        OpenClawCLIProvider: Configured provider instance.

    Example:
        provider = OpenClawCLIProvider(agent_name="nova", timeout_seconds=60)
    """

    def __init__(self, agent_name: str = "nova", timeout_seconds: int = 60) -> None:
        self.agent_name = agent_name
        self.timeout_seconds = timeout_seconds
        self.logger = logging.getLogger("nova")
        env_bin = os.environ.get("OPENCLAW_BIN", "").strip()
        # Fallback chain: env var → shutil.which → hardcoded brew path → bare command
        self.openclaw_bin = (
            env_bin
            or shutil.which("openclaw")
            or "/home/linuxbrew/.linuxbrew/bin/openclaw"
            or "openclaw"
        )
        self.logger.info(f"OpenClawCLIProvider initialized with bin={self.openclaw_bin}")

    def ask(self, message: str) -> AgentReply:
        """
        Send one text prompt to OpenClaw and return structured output.

        Args:
            message: User message after wake-word cleanup.

        Returns:
            AgentReply: Reply with success status and optional error details.

        Example:
            result = provider.ask("Status update")
        """
        if not message.strip():
            return AgentReply(text="", ok=False, error="empty_message")
        
        try:
            # Verify binary exists before running
            if not os.path.isfile(self.openclaw_bin):
                self.logger.error(f"OpenClaw binary not found at {self.openclaw_bin}")
                return AgentReply(text="", ok=False, error=f"openclaw_not_found:{self.openclaw_bin}")
            
            proc = subprocess.run(
                [
                    self.openclaw_bin,
                    "agent",
                    "--agent",
                    self.agent_name,
                    "--message",
                    message,
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            if proc.returncode != 0:
                self.logger.error(
                    "OpenClaw CLI failed",
                    extra={"stdout": proc.stdout[:500] if proc.stdout else None, "stderr": proc.stderr[:500] if proc.stderr else None, "returncode": proc.returncode, "openclaw_bin": self.openclaw_bin},
                )
                return AgentReply(text=message, ok=False, error=f"openclaw_cli_failed:returncode={proc.returncode}:stderr={proc.stderr[:200] if proc.stderr else 'none'}")

            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            # Filter out obvious echo/noise lines so we do not mirror user input as assistant output.
            candidates = []
            lowered_input = message.strip().lower()
            for line in lines:
                ll = line.lower()
                if ll == lowered_input:
                    continue
                if ll.startswith("you:") or ll.startswith("user:"):
                    continue
                if ll.startswith("thinking"):
                    continue
                candidates.append(line)
            if not candidates:
                self.logger.error(
                    "OpenClaw CLI produced no usable reply",
                    extra={"stdout": proc.stdout, "stderr": proc.stderr},
                )
                return AgentReply(text="", ok=False, error="openclaw_empty_reply")
            return AgentReply(text=candidates[-1], ok=True, error=None)
        except Exception as e:
            self.logger.exception("OpenClaw CLI exception", extra={"openclaw_bin": self.openclaw_bin, "error": str(e)})
            return AgentReply(text="", ok=False, error=f"openclaw_cli_exception:{self.openclaw_bin}:{type(e).__name__}:{str(e)[:50]}")
