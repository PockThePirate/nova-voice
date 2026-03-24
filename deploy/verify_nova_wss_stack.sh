#!/usr/bin/env bash
# Diagnose why wss://<host>/ws/audio/nova fails while HTTP works.
# Run on the app server (adjust MC_ROOT and PORT).

set -euo pipefail

MC_ROOT="${MC_ROOT:-$HOME/.openclaw/workspace/mission_control}"
PORT="${NOVA_ASGI_PORT:-8001}"
UNIT="${NOVA_ASGI_UNIT:-uvicorn-django-nova-asgi.service}"
VENV_UVICORN="$MC_ROOT/.venv/bin/uvicorn"

echo "=== Nova WSS stack check ==="
echo "MC_ROOT=$MC_ROOT  PORT=$PORT  UNIT=$UNIT"
echo

if [[ -d "$MC_ROOT" ]]; then
  echo "[OK] Mission Control directory exists"
else
  echo "[FAIL] Mission Control not found: $MC_ROOT"
  exit 1
fi

if [[ -x "$VENV_UVICORN" ]]; then
  echo "[OK] venv uvicorn: $VENV_UVICORN"
else
  echo "[WARN] No executable venv uvicorn at $VENV_UVICORN (pip install -r requirements.txt)"
fi

echo
echo "=== Python: import mission_control.asgi (gateway must load) ==="
if [[ -x "$MC_ROOT/.venv/bin/python" ]]; then
  if (cd "$MC_ROOT" && "$MC_ROOT/.venv/bin/python" -c "import mission_control.asgi as a; import sys; sys.exit(0 if a.nova_gateway_app is not None else 1)"); then
    echo "[OK] FastAPI gateway importable (nova_gateway_app set)"
  else
    echo "[FAIL] nova_gateway_app is None — install deps: cd $MC_ROOT && . .venv/bin/activate && pip install -r requirements.txt"
  fi
else
  echo "[SKIP] No venv python at $MC_ROOT/.venv/bin/python"
fi

echo
echo "=== systemd: $UNIT ==="
if systemctl is-active --quiet "$UNIT" 2>/dev/null; then
  echo "[OK] $UNIT is active"
  systemctl status "$UNIT" --no-pager -l | head -20 || true
else
  echo "[WARN] $UNIT not active (install deploy/uvicorn-django-nova-asgi.service)"
fi

echo
echo "=== Listen on 127.0.0.1:$PORT ==="
if command -v ss >/dev/null 2>&1; then
  if ss -lntp 2>/dev/null | grep -q ":$PORT "; then
    echo "[OK] Something is listening on $PORT"
    ss -lntp 2>/dev/null | grep ":$PORT " || true
  else
    echo "[FAIL] Nothing listening on 127.0.0.1:$PORT — start uvicorn ASGI"
  fi
else
  echo "[SKIP] ss not available"
fi

echo
echo "=== curl http://127.0.0.1:$PORT/ ==="
if curl -sS -o /dev/null -w "HTTP %{http_code}\n" --max-time 3 "http://127.0.0.1:$PORT/" || true; then
  :
else
  echo "[FAIL] curl could not reach backend"
fi

echo
echo "=== nginx (optional) ==="
if command -v nginx >/dev/null 2>&1; then
  sudo nginx -t 2>&1 || echo "[INFO] nginx -t failed or needs sudo"
else
  echo "[SKIP] nginx not in PATH"
fi

echo
echo "Done. Fix: nginx must include deploy/nginx-option-b-*.conf and proxy / to port $PORT with Upgrade headers."
echo "Then: sudo nginx -t && sudo systemctl reload nginx"
