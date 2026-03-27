# Headless Raspberry Pi Nova Listener

This bundle runs an always-on wake listener on a Raspberry Pi with no UI.

## Supported platform

- Raspberry Pi OS Bookworm (Debian 12) on ARM64/ARMHF.
- Installer exits early on non-Bookworm systems.

## What the installer provisions

System packages installed automatically:

- Core: `curl`, `ca-certificates`, `unzip`, `python3`, `python3-venv`, `python3-pip`
- Build/audio libs: `build-essential`, `pkg-config`, `libatlas-base-dev`, `libffi-dev`, `libasound2-dev`, `portaudio19-dev`
- Playback and diagnostics: `mpg123`, `ffmpeg`, `alsa-utils`

Runtime setup installed automatically:

- Python venv under `/opt/nova-voice-listener/.venv`
- Listener app under `/opt/nova-voice-listener`
- Vosk model under `/opt/vosk/vosk-model-small-en-us-0.15`
- Service file `nova-voice-listener.service` with `Restart=always`

## 1) Download from Mission Control

```bash
export NOVA_BASE_URL="https://your-mission-control-host"
export NOVA_GATEWAY_INTERNAL_TOKEN="I@mWho1\$@yIam$(date -u +%m%d)"
curl -fsSL -H "X-Nova-Gateway-Token: ${NOVA_GATEWAY_INTERNAL_TOKEN}" \
  "${NOVA_BASE_URL}/api/nova/device/bundle" -o nova-raspberry-pi-bundle.tar.gz
```

## 2) Install on Raspberry Pi

```bash
tar -xzf nova-raspberry-pi-bundle.tar.gz
cd raspberry_pi
sudo bash install.sh
```

## 3) Configure runtime token and host

Edit `/etc/nova-voice.env` and set required values:

- `NOVA_BASE_URL`
- `NOVA_GATEWAY_INTERNAL_TOKEN`
- `NOVA_VOSK_MODEL_PATH`

Then restart:

```bash
sudo systemctl restart nova-voice-listener.service
```

## 4) Verify installation

```bash
sudo /opt/nova-voice-listener/.venv/bin/python -m nova_listener.main --self-check
sudo systemctl status nova-voice-listener.service --no-pager
sudo journalctl -u nova-voice-listener.service -n 100 --no-pager
```

Installer smoke checks (when host/token are set to real values) write:

- `/tmp/nova-device-bundle-smoke.tar.gz`
- `/tmp/nova-voice-internal-smoke.json`
- `/tmp/nova-device-audio-smoke.mp3`

## 5) Service management

```bash
sudo systemctl status nova-voice-listener.service
sudo journalctl -u nova-voice-listener.service -f
```

## Security notes

- Always terminate TLS at your reverse proxy and use `https://...` in `NOVA_BASE_URL`.
- The `I@mWho1$@yIamMMDD` pattern is predictable; use firewall allow-listing and rotate regularly.
- Keep `/etc/nova-voice.env` permissions at `600`.

## Mission Control server settings

Set on the Mission Control host:

- `NOVA_GATEWAY_INTERNAL_TOKEN` (recommended explicit shared secret)
- Optional fallback mode: `NOVA_DEVICE_TOKEN_DERIVED=true` when you want server-side `I@mWho1$@yIamMMDD` derivation and no explicit token

## Troubleshooting

- No microphone detected:
  - `arecord -l`
  - update default ALSA device or USB mic selection
- Audio playback fails:
  - `which mpg123`
  - test with `mpg123 /tmp/nova-device-audio-smoke.mp3`
- Service loops on boot:
  - `sudo journalctl -u nova-voice-listener.service -f`
  - run self-check manually to inspect environment validation errors

