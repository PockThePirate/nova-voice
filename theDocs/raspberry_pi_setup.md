# Raspberry Pi Headless Nova Setup (Bookworm)

This guide installs and runs the headless Nova listener on a Raspberry Pi with auto-start on boot and restart on crash.

## Prerequisites

- Raspberry Pi OS Bookworm
- Network access to your Mission Control host
- HTTPS enabled on Mission Control
- Matching gateway token on both server and Pi

---

## 1) Configure token on Mission Control server

Set and persist your token in the Mission Control service environment:

```bash
NOVA_GATEWAY_INTERNAL_TOKEN='I@mWho1$@yIam'"$(date -u +%m%d)"
```

Restart Mission Control services after updating env vars.

---

## 2) Download bundle on Raspberry Pi

```bash
export NOVA_BASE_URL='https://your-mission-control-host'
export NOVA_GATEWAY_INTERNAL_TOKEN='I@mWho1$@yIam'"$(date -u +%m%d)"

curl -fsSL -H "X-Nova-Gateway-Token: $NOVA_GATEWAY_INTERNAL_TOKEN" \
  "$NOVA_BASE_URL/api/nova/device/bundle" -o nova-raspberry-pi-bundle.tar.gz
```

---

## 3) Extract and install

```bash
tar -xzf nova-raspberry-pi-bundle.tar.gz
cd raspberry_pi
sudo bash install.sh
```

Installer tasks include:

- apt system dependency install
- Python venv setup
- Vosk model download/extract
- systemd service install
- enable/start service (`nova-voice-listener.service`)

---

## 4) Configure runtime environment on Pi

Edit:

```bash
sudo nano /etc/nova-voice.env
```

Set at minimum:

```ini
NOVA_BASE_URL=https://your-mission-control-host
NOVA_GATEWAY_INTERNAL_TOKEN=I@mWho1$@yIamMMDD
NOVA_VOSK_MODEL_PATH=/opt/vosk/vosk-model-small-en-us-0.15
NOVA_VOSK_SAMPLE_RATE=16000
NOVA_COMMAND_SILENCE_SECONDS=3.75
NOVA_MAX_COMMAND_SECONDS=30
NOVA_WAKE_PHRASES=nova,hey nova
NOVA_AUDIO_PLAYER_CMD=mpg123 -q {path}
```

Restart service:

```bash
sudo systemctl restart nova-voice-listener.service
```

---

## 5) Verify service health

```bash
sudo systemctl status nova-voice-listener.service --no-pager
sudo journalctl -u nova-voice-listener.service -f
```

Optional self-check:

```bash
sudo /opt/nova-voice-listener/.venv/bin/python -m nova_listener.main --self-check
```

---

## 6) Reboot persistence check

```bash
sudo reboot
# after reconnect:
sudo systemctl status nova-voice-listener.service --no-pager
```

Service should come up automatically.

---

## Troubleshooting

### Token/auth failures

- Ensure Pi and server use the same `NOVA_GATEWAY_INTERNAL_TOKEN`
- Confirm server env is updated and services restarted

### No microphone input

```bash
arecord -l
```

Check ALSA device selection and USB mic connection.

### Playback issues

```bash
which mpg123
```

Test playback with a known MP3 file.

### Service crash loop

```bash
sudo journalctl -u nova-voice-listener.service -n 200 --no-pager
```

Fix env/model/audio errors shown in logs.

---

## Security notes

- Use HTTPS for all requests
- Keep `/etc/nova-voice.env` permission `600`
- The `I@mWho1$@yIamMMDD` format is predictable; prefer firewall allowlists and regular rotation
