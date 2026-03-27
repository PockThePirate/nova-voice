"""Entrypoint for the headless Raspberry Pi Nova listener."""

from __future__ import annotations

import argparse
import sys

from .client import NovaApiClient
from .config import ListenerConfig
from .listener import HeadlessNovaListener


class NovaListenerApp:
    """
    General purpose: Compose config, API client, and listener runtime.

    Args:
        None

    Returns:
        NovaListenerApp: Service container for one process instance.

    Example:
        app = NovaListenerApp()
    """

    def __init__(self) -> None:
        self.config = ListenerConfig.from_env()
        self.config.validate()
        self.client = NovaApiClient(
            base_url=self.config.base_url,
            gateway_token=self.config.gateway_token,
        )
        self.listener = HeadlessNovaListener(self.config, self.client)

    def run(self) -> None:
        """
        General purpose: Run the listener event loop until process termination.

        Args:
            None

        Returns:
            None

        Example:
            app.run()
        """
        self.listener.run_forever()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """
    General purpose: Parse CLI flags for runtime and installer self-check flow.

    Args:
        argv (list[str] | None): Optional argument list override.

    Returns:
        argparse.Namespace: Parsed arguments.

    Example:
        args = parse_args(["--self-check"])
    """
    parser = argparse.ArgumentParser(description="Headless Nova listener runtime.")
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Validate environment and exit (no mic capture).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    General purpose: CLI entrypoint used by systemd service command.

    Args:
        argv (list[str] | None): Optional argument list override.

    Returns:
        int: Process exit code.

    Example:
        raise SystemExit(main())
    """
    args = parse_args(argv)
    try:
        app = NovaListenerApp()
    except Exception as exc:
        print(f"[nova-listener] startup validation failed: {exc}", file=sys.stderr)
        return 2
    if args.self_check:
        print("[nova-listener] self-check passed")
        return 0
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

