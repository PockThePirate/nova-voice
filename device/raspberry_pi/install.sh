#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="/opt/nova-voice-listener"
VENV_PATH="${APP_ROOT}/.venv"
ENV_FILE="/etc/nova-voice.env"
SERVICE_NAME="nova-voice-listener.service"
MODEL_DIR="/opt/vosk/vosk-model-small-en-us-0.15"
MODEL_URL="https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
APT_PACKAGES=(
  curl ca-certificates unzip python3 python3-venv python3-pip
  build-essential pkg-config libatlas-base-dev libffi-dev
  libasound2-dev portaudio19-dev mpg123 ffmpeg alsa-utils
)

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run as root: sudo bash install.sh"
  exit 1
fi

if [[ ! -f /etc/os-release ]]; then
  echo "Cannot determine OS (missing /etc/os-release)."
  exit 1
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "debian" && "${ID:-}" != "raspbian" ]]; then
  echo "Unsupported OS ID: ${ID:-unknown}. This installer targets Raspberry Pi OS Bookworm."
  exit 1
fi
if [[ "${VERSION_CODENAME:-}" != "bookworm" ]]; then
  echo "Unsupported codename: ${VERSION_CODENAME:-unknown}. Required: bookworm."
  exit 1
fi

if ! curl -fsSL --max-time 10 "https://pypi.org/simple/" >/dev/null; then
  echo "Network preflight failed: cannot reach pypi.org"
  exit 1
fi
if ! curl -fsSL --max-time 10 "${MODEL_URL}" -o /dev/null; then
  echo "Network preflight failed: cannot reach Vosk model URL"
  exit 1
fi

apt-get update
apt-get install -y "${APT_PACKAGES[@]}"

mkdir -p "${APP_ROOT}"
cp -r "${SCRIPT_DIR}/nova_listener" "${APP_ROOT}/"
cp "${SCRIPT_DIR}/requirements.txt" "${APP_ROOT}/requirements.txt"

python3 -m venv "${VENV_PATH}"
"${VENV_PATH}/bin/pip" install --upgrade pip
"${VENV_PATH}/bin/pip" install -r "${APP_ROOT}/requirements.txt"

mkdir -p /opt/vosk
if [[ ! -d "${MODEL_DIR}" ]]; then
  TMP_ZIP="$(mktemp /tmp/vosk-model.XXXXXX.zip)"
  curl -fsSL "${MODEL_URL}" -o "${TMP_ZIP}"
  if [[ ! -s "${TMP_ZIP}" ]]; then
    echo "Downloaded Vosk model archive is empty."
    exit 1
  fi
  python3 - <<'PY' "${TMP_ZIP}"
import sys
import zipfile
from pathlib import Path

zip_path = Path(sys.argv[1])
dest = Path("/opt/vosk")
with zipfile.ZipFile(zip_path, "r") as zf:
    zf.extractall(dest)
zip_path.unlink(missing_ok=True)
print("Extracted Vosk model to /opt/vosk")
PY
fi
if [[ ! -d "${MODEL_DIR}" || ! -f "${MODEL_DIR}/am/final.mdl" ]]; then
  echo "Vosk model validation failed after extraction."
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  cat > "${ENV_FILE}" <<'EOF'
NOVA_BASE_URL=https://your-mission-control-host
NOVA_GATEWAY_INTERNAL_TOKEN=I@mWho1$@yIam0101
NOVA_VOSK_MODEL_PATH=/opt/vosk/vosk-model-small-en-us-0.15
NOVA_VOSK_SAMPLE_RATE=16000
NOVA_COMMAND_SILENCE_SECONDS=3.75
NOVA_MAX_COMMAND_SECONDS=30
NOVA_WAKE_PHRASES=nova,hey nova
NOVA_AUDIO_PLAYER_CMD=mpg123 -q {path}
EOF
  chmod 600 "${ENV_FILE}"
fi

cp "${SCRIPT_DIR}/systemd/${SERVICE_NAME}" "/etc/systemd/system/${SERVICE_NAME}"
chmod 644 "/etc/systemd/system/${SERVICE_NAME}"

if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify "/etc/systemd/system/${SERVICE_NAME}" || true
fi

"${VENV_PATH}/bin/python" -m nova_listener.main --self-check

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
systemctl status "${SERVICE_NAME}" --no-pager

if grep -q '^NOVA_BASE_URL=' "${ENV_FILE}" && grep -q '^NOVA_GATEWAY_INTERNAL_TOKEN=' "${ENV_FILE}"; then
  base_url="$(grep '^NOVA_BASE_URL=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2-)"
  token="$(grep '^NOVA_GATEWAY_INTERNAL_TOKEN=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2-)"
  if [[ -n "${base_url}" && -n "${token}" && "${base_url}" != "https://your-mission-control-host" ]]; then
    echo "Running endpoint smoke checks..."
    curl -fsSL -H "X-Nova-Gateway-Token: ${token}" "${base_url}/api/nova/device/bundle" -o /tmp/nova-device-bundle-smoke.tar.gz || true
    curl -fsSL -H "X-Nova-Gateway-Token: ${token}" -X POST "${base_url}/api/nova/voice/internal/" -d "text=health check from pi installer" -o /tmp/nova-voice-internal-smoke.json || true
    python3 - <<'PY' "${base_url}" "${token}" /tmp/nova-voice-internal-smoke.json
import json
import re
import sys
import urllib.request
from pathlib import Path

base_url = sys.argv[1].rstrip("/")
token = sys.argv[2]
payload_path = Path(sys.argv[3])
if not payload_path.exists():
    raise SystemExit(0)
try:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
audio_url = str(payload.get("audio_url", "")).strip()
match = re.search(r"([0-9a-fA-F-]{36}\.mp3)", audio_url)
if not match:
    raise SystemExit(0)
filename = match.group(1)
req = urllib.request.Request(
    f"{base_url}/api/nova/audio/device/{filename}",
    headers={"X-Nova-Gateway-Token": token},
)
with urllib.request.urlopen(req, timeout=30) as resp:
    payload = resp.read()
Path("/tmp/nova-device-audio-smoke.mp3").write_bytes(payload)
print("Device audio endpoint smoke check passed.")
PY
  fi
fi

echo
echo "Installed. Edit ${ENV_FILE} then run:"
echo "  sudo systemctl restart ${SERVICE_NAME}"

