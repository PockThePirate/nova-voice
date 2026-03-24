"""
Management command: verify local prerequisites for Nova mic WebSocket (ASGI + port).

Example:
    cd mission_control && .venv/bin/python manage.py nova_check_deploy
    NOVA_ASGI_PORT=8001 .venv/bin/python manage.py nova_check_deploy
"""

import os
import socket
import sys
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    Print whether FastAPI gateway imports in ASGI and whether a TCP port accepts connections.

    Attributes:
        help (str): Short description for ``manage.py help``.

    Example:
        ``python manage.py nova_check_deploy``
    """

    help = "Check Nova WebSocket prerequisites (ASGI gateway import + ASGI listen port)."

    def add_arguments(self, parser):
        """
        Register command-line arguments.

        Args:
            parser: argparse.ArgumentParser from Django.

        Returns:
            None

        Example:
            ``manage.py nova_check_deploy --port 8001``
        """
        parser.add_argument(
            "--port",
            type=int,
            default=8001,
            help="TCP port nginx should proxy to (default 8001).",
        )

    def handle(self, *args, **options):
        """
        Run checks and print results to stdout.

        Args:
            *args: Positional arguments (unused).
            **options: Parsed options including ``port``.

        Returns:
            None

        Example:
            Called by Django when user runs ``manage.py nova_check_deploy``.
        """
        port = int(options["port"])
        self.stdout.write("=== Nova WebSocket / ASGI deploy check ===\n")

        proj_root = Path(__file__).resolve().parents[3]
        workspace_root = proj_root.parent
        env_gw = os.environ.get("NOVA_AUDIO_GATEWAY_ROOT", "").strip()
        gateway_dir = Path(env_gw) if env_gw else (workspace_root / "nova-audio-gateway")
        gateway_ok = False
        if gateway_dir.is_dir():
            gw = str(gateway_dir)
            if gw not in sys.path:
                sys.path.insert(0, gw)
            try:
                import fastapi  # noqa: F401

                from app import app as _nova_app  # noqa: F401

                gateway_ok = True
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(
                        f"Gateway dir {gateway_dir}: import failed ({exc}) — pip install -r requirements.txt"
                    )
                )
        else:
            self.stdout.write(self.style.ERROR(f"Gateway dir missing: {gateway_dir}"))
        if gateway_ok:
            self.stdout.write(
                self.style.SUCCESS("Gateway: FastAPI app import OK (same layout as mission_control.asgi expects).")
            )

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.5)
        try:
            sock.connect(("127.0.0.1", port))
            self.stdout.write(
                self.style.SUCCESS(f"TCP: 127.0.0.1:{port} accepts connections (uvicorn likely running).")
            )
        except OSError:
            self.stdout.write(
                self.style.ERROR(
                    f"TCP: nothing listening on 127.0.0.1:{port} — start ASGI, e.g.\n"
                    f"  cd $(dirname manage.py) && .venv/bin/uvicorn mission_control.asgi:application "
                    f"--host 127.0.0.1 --port {port}"
                )
            )
        finally:
            sock.close()

        self.stdout.write(
            "\nIf TCP is OK but the browser still fails WSS: nginx must proxy HTTPS location / "
            "to that port WITH WebSocket headers (map + Upgrade + Connection $connection_upgrade). "
            "See deploy/CHECKLIST-NOVA-WSS.txt and deploy/nginx-option-b-*.conf.\n"
            "Typed Send can work via gunicorn while mic fails if / still goes to WSGI only.\n"
        )
