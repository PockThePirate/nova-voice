# Nova Mission Control – Goals & Purpose

## 1. High-Level Goal

Create a **web-based Mission Control dashboard** (and matching clients) that makes Nova usable as a hands‑free, commute‑friendly voice assistant, while also exposing richer controls:

- Voice interaction with Nova via WebSocket audio streaming (`/ws/audio/nova`)
- Text interaction via a simple message box (`/api/nova/voice/` / `nova_voice_api`)
- Mission management: logs, focus, next actions
- Timeline of events and debug/diagnostic output
- A UX that works well on **mobile (Android browser)** and desktop.

## 2. Current Focus

Right now we are specifically working on:

1. **Android-friendly Push-To-Talk (PTT) flow in Mission Control**
   - Big round button that:
     - **First tap** → starts recording via `NovaStreamClient` (WebSocket + mic capture)
     - **Second tap** → stops recording and sends the audio to the backend
   - This replaces the browser’s hold-to-talk behavior, which does **not** work well on Android (long-press / pointer events are unreliable across browsers).

2. **Inline console for client-side logs**
   - A "Console" panel on the Mission Control dashboard showing `console.log/info/warn/error` output.
   - Helps debug behavior directly on mobile without needing DevTools.

## 3. What We Have Built So Far

### 3.1 Dashboard Structure

File: `templates/dashboard/dashboard.html`

- Top row: **Mission Control status**, active missions count, agents count.
- Panels for:
  - **Today’s Focus** (focus mission, next actions)
  - **Mission Logs** (file-based mission artifacts)
  - **Voice Agents** (wake words, modes, enable/disable)
  - **Mission Timeline** (last 20 events)
  - **Console** (client-side JS logs)

### 3.2 Voice UI – Text Path

- Form: `#nova-voice-form` with `data-nova-ajax-submit="true"`.
- Text input + "Send" button.
- Handled in `static/js/nova.js`:
  - Submits via AJAX to `nova_voice_api`.
  - Updates status with `reply_text`.
  - Plays TTS audio if `audio_url` is returned.
- This path is **working** and is our baseline for interaction.

### 3.3 Voice UI – Streaming Path (NovaStreamClient)

File: `static/js/nova_stream.js`

- `NovaStreamClient` handles:
  - WebSocket connection to `/ws/audio/nova` (or overridden `wsUrl`)
  - JSON `start/stop` control messages with `session_id` and `sample_rate`
  - Mic capture via AudioWorklet or ScriptProcessor
  - Downsampling to 16 kHz mono Int16 PCM and sending binary frames
  - Client-side silence detection (`onSilence` callback) after ~2 seconds

### 3.4 PTT Button UX

Template:

```html
<button type="button" class="ptt-button" id="nova-ptt-btn">🎙<br>Nova</button>
<div id="nova-mic-status" class="nova-mic-status" aria-live="polite">Tap to speak</div>
<p class="nova-mic-hint">Tap the round button to start recording. Tap again to stop and send.</p>
```

Styles (`static/css/cyber.css`):

- `.ptt-button` is a **large round button** (~120×120px) with glowing borders.
- `.ptt-button.recording` is the active state (filled, pulsing glow) while streaming.

Behavior (`static/js/nova.js`):

- `micToggleBtn` = `#nova-ptt-btn`.
- PTT mode logic:
  - `handleMicToggleClick()`:
    - Logs `[PTT] mic toggle clicked; streamClient is ...`.
    - If `streamClient` exists → `handleStopClick()`.
    - Else → `handleStartClick()`.
  - `handleStartClick()`:
    - Checks `canUseStream()` → `NovaStreamClient` must be defined.
    - Creates `new NovaStreamClient({ path: wsPath })` or `{ wsUrl }`.
    - Sets `streamClient.onReady` to call `startCapture()`.
    - Sets `onSilence` to call `handleStopClick()`.
    - Sets `onConnectionLost` and `onMessage` for status updates.
  - `handleStopClick()`:
    - If `streamClient`, calls `disconnect()` and clears it.
    - Calls `setUiStreaming(false)` and sets status to `"Query sent…"`.
  - `setUiStreaming(streaming)`:
    - Updates PTT button label: `"Tap to speak"` or `"Tap to send"`.
    - Adds/removes `.recording` class for visual state.

### 3.5 Inline Console

Template: **Console panel** with Clear + Copy buttons.

Styles (`cyber.css`): `.console-panel`, `.console-line-*` for colors.

JS (`nova.js`):

- Wraps `console.log/info/warn/error` with a function that:
  - Renders `[KIND] message` lines into `#nova-console`.
  - Keeps original console behavior for DevTools.
- Clear button empties `#nova-console`.
- Copy button uses `navigator.clipboard.writeText` to copy all console text.

## 4. What We Tried (Wake Word & Vosk)

We attempted to integrate **Vosk** (offline ASR) in the browser for wake-word detection:

- Added `static/js/nova_wake_vosk.js` as a Vosk engine wrapper.
- Downloaded `vosk-browser` via npm, copied `vosk.js` into `static/js/`.
- Placed the Vosk model under `static/vosk/model-en/vosk-model-small-en-us-0.15` and packaged it as `vosk-model-small-en-us-0.15.tar.gz`.
- Wired `NovaWakeEngine.init()` to call `Vosk.createModel(modelPath)` and create a `KaldiRecognizer`.
- Hooked `NovaWakeEngine.process()` to feed audio frames.
- Wired `NovaWakeEngine.setOnWake()` to call the same handler that starts streaming.

Outcome:

- Integration is partly in place, but wake-word behavior wasn’t reliable enough, and Android browser constraints make continuous mic access awkward.
- For now, **we pivoted to explicit PTT mode** for mobile reliability.

## 5. Current Status & Observed Behavior (PTT)

### 5.1 Observed in Console

After first tap on the PTT button:

- We see:

  ```
  [INFO] [Nova] WebSocket connecting: wss://novamission.cloud/ws/audio/nova (DevTools: Network, enable Preserve log, filter WS, then Wake Nova)
  ```

- This confirms:
  - `handleStartClick()` is being invoked.
  - `NovaStreamClient.connect()` is called.

After second tap:

- **Expected**: `handleStopClick()` logs, `Query sent…` status, and `.recording` class removed.
- **Observed**: nothing significant changes in the UI; no additional console lines for stop.

This suggests one of:

- `streamClient` may not be set as expected, so second tap may call `handleStartClick()` again.
- Or `handleStopClick()` is called but something prevents UI updates.

Additional `[PTT]` debug logs are being added to `nova.js` to pinpoint which branches execute.

## 6. Deployment: nginx + uvicorn (ASGI)

Mission Control is deployed using **nginx** as the public reverse proxy and **uvicorn** (ASGI) as the Django+WebSocket application server.

### 6.1 Process layout

- **uvicorn-django-nova-asgi.service** (systemd):
  - Runs `uvicorn mission_control.asgi:application` inside the project venv.
  - Handles both:
    - Regular HTTP requests for Django views (dashboard, missions, API endpoints), and
    - WebSocket connections for `/ws/audio/nova` when using the combined-ASGI setup.

- **nginx**:
  - Terminates TLS for `https://novamission.cloud`.
  - Proxies:
    - `location /` → uvicorn (Mission Control ASGI app)
    - Ensures `Upgrade` / `Connection` headers are passed through for WebSockets so `/ws/audio/nova` works.

### 6.2 Why this architecture

- A single ASGI process (uvicorn) simplifies routing:
  - Django HTTP and Nova WebSockets share the same process and URL space.
  - The browser can use a **relative** path `/ws/audio/nova`, and nginx forwards both HTTP and WS to uvicorn.
- nginx is responsible for:
  - SSL/TLS offload.
  - Serving static assets from `staticfiles/` when configured.
  - Handling any additional sites/virtual hosts on the same server.

### 6.3 Relevant deploy files

Under `mission_control/deploy/`:

- `uvicorn-django-nova-asgi.service` / `uvicorn-django-nova-asgi.service.pock`:
  - Example systemd unit files used to start/stop the ASGI server.

- `nginx-site-mission_control.conf` and `nginx-option-b-*.conf` snippets:
  - Show how to configure nginx to:
    - Proxy `/` to uvicorn.
    - Correctly handle `Upgrade`/`Connection` headers for WebSocket traffic.

- `nova-websocket-nginx.conf.example`:
  - Additional reference for different deployment options (separate gateway vs combined ASGI).

### 6.4 Operational notes

- When we change static assets (JS/CSS):
  - Run `collectstatic` to sync `static/` → `staticfiles/`.
  - Ensure nginx is configured to serve from `staticfiles/` or let Django/uvicorn serve from there.

- When we change Python/Django or ASGI wiring:
  - Restart the uvicorn systemd service:

    ```bash
    sudo systemctl restart uvicorn-django-nova-asgi
    ```

- When we change nginx config:
  - Test & reload nginx:

    ```bash
    sudo nginx -t && sudo systemctl reload nginx
    ```

## 7. Common Errors / Pitfalls We Hit

1. **Static files out of sync**
   - Editing files under `static/` requires running:

     ```bash
     cd /home/pock/.openclaw/workspace/mission_control
     source .venv/bin/activate
     python manage.py collectstatic --noinput
     deactivate
     ```

   - Forgetting this can leave the browser using older versions from `staticfiles/`.

2. **ID mismatches between template and JS**
   - JS expected `#nova-mic-status`, template originally had `#nova-ptt-status`.
   - Result: status text and streaming label didn’t update even though logic ran.
   - Fixed by aligning IDs in the template.

3. **WebSocket configuration / proxying**
   - The dashboard assumes `/ws/audio/nova` is reachable on the same host via `wss://novamission.cloud/ws/audio/nova`.
   - If nginx or uvicorn routing is misconfigured, you’ll see connection failures or no audio on the backend.

4. **Android browser quirks**
   - Long-press / hold-to-talk interactions don’t map cleanly across mobile browsers.
   - Permissions for `getUserMedia` can be flaky, especially if the page isn’t served over HTTPS.
   - This led to the decision to prioritize **tap-to-toggle PTT** instead of hold-to-talk.

5. **Vosk WebAssembly and model paths**
   - `vosk-browser` expects model paths as tar.gz archives (`model.tar.gz`).
   - Initial attempts used folder paths, leading to load failures.
   - Also, remote package URLs changed (404s from older repos), so we had to fetch Vosk via npm instead of GitHub releases.

## 8. Next Steps

1. **PTT reliability verification**
   - Validate deterministic state transitions logged as `[PTT_STATE]`:
     - `idle -> starting -> recording -> stopping -> idle`
   - Validate second tap always executes stop and UI reset.

2. **Protocol observability verification**
   - Confirm `/ws/audio/nova` emits `start_ack` and `stop_ack`.
   - Confirm `stop_ack` includes session metrics (`frames`, `bytes`, `duration_ms`) for diagnostics.

3. **Service-layer hardening**
   - Keep `nova_voice_api` thin and continue building around class-based services:
     - `OpenClawCLIProvider`
     - `EdgeTTSProvider`
     - `VoiceOrchestrator`
   - Preserve response contract (`reply_text`, `audio_url`) while adding richer internal error handling.

4. **Optional future: wake-word on desktop**
   - Keep Vosk wake-word optional for desktop browsers where continuous mic access is acceptable.
   - Maintain PTT as default on mobile for reliability.

---

This file is a living document. Update it as we refine PTT behavior, add Mission APIs for the Android app, or change the architecture.
