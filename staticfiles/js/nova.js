/**
 * Binds `#nova-voice-form` to NovaStreamClient (mic toggle), optional AJAX POST to
 * `nova_voice_api`, and `window.NOVA_STREAM_FAILED` tracking.
 *
 * Expected markup:
 * - form#nova-voice-form with action pointing at nova voice API for AJAX submit
 * - optional data-nova-ajax-submit="true"
 * - optional data-nova-ws-path, data-nova-ws-url (full ws/wss URL for dev)
 * - #nova-mic-btn with data-nova-mic-toggle for start/stop streaming
 * - #nova-mic-status for user-facing status and reply preview
 */
(function () {
  "use strict";

  const MIC_LABEL_IDLE = "Tap to speak";
  const MIC_LABEL_ACTIVE = "Tap to send";

  /** Max wait after PTT stop for WebSocket reply (PTT only; wake uses HTTP fetch). */
  const NOVA_WS_REPLY_TIMEOUT_MS = 120000;

  const form = document.getElementById("nova-voice-form");
  if (!form) {
    return;
  }

  const statusEl = document.getElementById("nova-mic-status");
  const playReplyBtn = document.getElementById("nova-play-reply-btn");
  var lastReplyAudioUrl = "";
  var replyPlayer = null;
  var audioPrimed = false;

  /**
   * Show short status in `#nova-mic-status`.
   * @param {string} message Plain text
   */
  function setStatus(message) {
    if (statusEl) {
      statusEl.textContent = message || "";
    }
  }

  /**
   * Show or hide the manual Play reply control.
   * @param {boolean} visible Whether the button should be visible
   */
  function setPlayReplyVisible(visible) {
    if (playReplyBtn) {
      playReplyBtn.classList.toggle("nova-play-reply-hidden", !visible);
    }
  }

  /**
   * Reuse one Audio element for Nova replies (helps autoplay policies).
   * @returns {HTMLAudioElement}
   */
  function getReplyPlayer() {
    if (!replyPlayer) {
      replyPlayer = new Audio();
    }
    return replyPlayer;
  }

  /**
   * Run during a user gesture (PTT tap, Send click) to improve later programmatic play.
   * @returns {void}
   */
  function primeAudioPlaybackFromUserGesture() {
    if (audioPrimed) {
      return;
    }
    var a = getReplyPlayer();
    a.src =
      "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA";
    a.volume = 0.001;
    var p = a.play();
    if (p && typeof p.then === "function") {
      p.then(function () {
        a.pause();
        a.currentTime = 0;
        a.volume = 1;
        audioPrimed = true;
      }).catch(function () {
        /* ignore; browser may still allow real clip later */
      });
    }
  }

  /**
   * Map legacy unserved ``/static/nova_audio/*.mp3`` URLs to the Django streamer path.
   * @param {string} audioUrl URL from JSON (path or full origin URL)
   * @returns {string}
   */
  function normalizeNovaAudioUrl(audioUrl) {
    if (!audioUrl || typeof audioUrl !== "string") {
      return audioUrl;
    }
    var marker = "/static/nova_audio/";
    var idx = audioUrl.indexOf(marker);
    if (idx === -1) {
      return audioUrl;
    }
    var name = audioUrl.slice(idx + marker.length).split("?")[0];
    if (!name) {
      return audioUrl;
    }
    return "/api/nova/audio/" + name;
  }

  /**
   * Attempt reply audio playback; on failure show Play reply and log the error.
   * @param {string} audioUrl Static audio URL returned by Nova API
   */
  function playReplyAudio(audioUrl) {
    if (!audioUrl) {
      setPlayReplyVisible(false);
      return;
    }
    var resolved = normalizeNovaAudioUrl(audioUrl);
    lastReplyAudioUrl = resolved;
    setPlayReplyVisible(true);
    var player = getReplyPlayer();
    player.src = resolved;
    var playPromise = player.play();
    if (playPromise && typeof playPromise.then === "function") {
      playPromise
        .then(function () {
          setPlayReplyVisible(false);
        })
        .catch(function (playErr) {
          console.error("Nova audio play error:", playErr);
          setStatus('Tap "Play reply" to hear Nova (autoplay blocked).');
        });
    }
  }

  /**
   * Read a cookie by name (e.g. Django `csrftoken`).
   * @param {string} name Cookie name
   * @returns {string|null} Decoded value or null
   */
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === name + "=") {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  if (typeof window.NOVA_STREAM_FAILED === "undefined") {
    window.NOVA_STREAM_FAILED = false;
  }

  let streamClient = null;
  let streamState = "idle"; // idle | starting | recording | stopping
  let wsReplyPending = false;
  let stopTimeoutId = null;

  const wsPath = form.getAttribute("data-nova-ws-path") || "/ws/audio/nova";
  const wsUrlAttr = form.getAttribute("data-nova-ws-url");
  const wsUrl =
    wsUrlAttr && (wsUrlAttr.indexOf("ws:") === 0 || wsUrlAttr.indexOf("wss:") === 0) ? wsUrlAttr : null;

  const startBtn = null; // not used in PTT mode
  const stopBtn = null;  // not used in PTT mode
  const micToggleBtn = document.getElementById("nova-ptt-btn");
  const useMicToggle = !!micToggleBtn;

  // No wake-word engine in PTT mode; tap to start/stop streaming instead.
  let wakeClient = null;

  /**
   * Whether WebSocket streaming is available right now (lazy; scripts may load in any order).
   * @returns {boolean}
   */
  function canUseStream() {
    return typeof WebSocket !== "undefined" && typeof window.NovaStreamClient === "function";
  }

  /**
   * @param {boolean} streaming
   */
  function setUiStreaming(streaming) {
    if (useMicToggle && micToggleBtn) {
      micToggleBtn.disabled = false;
      micToggleBtn.textContent = streaming ? MIC_LABEL_ACTIVE : MIC_LABEL_IDLE;
      if (streaming) {
        micToggleBtn.classList.add("recording");
      } else {
        micToggleBtn.classList.remove("recording");
      }
    }
  }

  /**
   * Set internal stream lifecycle state and emit structured diagnostics.
   * @param {string} nextState Target state value
   * @param {string} reason Human-readable reason
   */
  function setStreamState(nextState, reason) {
    streamState = nextState;
    console.info("[PTT_STATE]", { state: nextState, reason: reason || "" });
  }

  function clearStopTimeout() {
    if (stopTimeoutId) {
      window.clearTimeout(stopTimeoutId);
      stopTimeoutId = null;
    }
  }

  function finalizePendingStop(reason) {
    clearStopTimeout();
    wsReplyPending = false;
    if (streamClient) {
      streamClient.closeSocket();
      streamClient = null;
    }
    setStreamState("idle", reason || "stop_finalized");
  }

  function teardownStream() {
    if (streamClient) {
      streamClient.disconnect();
      streamClient = null;
    }
    setStreamState("idle", "teardown");
    setUiStreaming(false);
    setStatus("");
  }

  /**
   * POST form body with CSRF to a URL.
   * @param {string} url Absolute or same-origin URL
   * @param {FormData} body Form fields
   * @returns {Promise<Response>}
   */
  function postToUrl(url, body) {
    const method = "POST";
    const headers = { Accept: "application/json" };
    const token = getCookie("csrftoken");
    if (token) {
      headers["X-CSRFToken"] = token;
    }
    return fetch(url, {
      method: method,
      body: body,
      headers: headers,
      credentials: "same-origin",
    });
  }

  async function handleStartClick() {
    if (streamState === "starting" || streamState === "recording") {
      console.info("[PTT] ignoring start; active state:", streamState);
      return;
    }
    primeAudioPlaybackFromUserGesture();
    if (!canUseStream()) {
      window.NOVA_STREAM_FAILED = true;
      setStatus("Voice stream unavailable (WebSocket client not loaded).");
      return;
    }
    setStreamState("starting", "tap_start");
    setUiStreaming(true);
    setStatus("Connecting…");
    let voiceWsOpened = false;
    try {
      streamClient = new window.NovaStreamClient(wsUrl ? { wsUrl: wsUrl } : { path: wsPath });
      streamClient.onConnectionLost = function (ev) {
        streamClient = null;
        clearStopTimeout();
        wsReplyPending = false;
        setStreamState("idle", "connection_lost");
        setUiStreaming(false);
        if (!voiceWsOpened) {
          setStatus(
            "Voice stream unavailable: use combined ASGI (uvicorn mission_control.asgi:application + nginx Upgrade on /) " +
              "or proxy /ws/audio/nova to a gateway. See deploy/nova-websocket-nginx.conf.example (Option B). Typed Send still works."
          );
        } else {
          setStatus("Disconnected.");
        }
        voiceWsOpened = false;
      };
      // Disable auto-stop on silence - user must manually tap to stop
      // This ensures we capture enough audio for transcription
      streamClient.onSilence = function () {
        // Silently ignore - wait for manual stop
      };
      streamClient.onMessage = function (event) {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "status" && data.state === "listening") {
            setStreamState("recording", "server_listening");
            setStatus("Listening…");
          } else if (data.type === "status" && data.state === "idle") {
            setStreamState("idle", "server_idle");
            if (wsReplyPending) {
              setStatus("Processing ended without a reply. Check gateway logs.");
              finalizePendingStop("server_idle_without_reply");
            }
          } else if (data.type === "status" && data.event === "stop_ack") {
            setStatus("Stop received. Processing...");
          } else if (data.type === "status" && data.state === "processing" && data.event === "transcribing_started") {
            setStatus("Transcribing...");
          } else if (data.type === "status" && data.state === "processing" && data.event === "transcribing_done") {
            if (data.transcript) {
              setStatus('Heard: "' + data.transcript + '"');
            } else {
              setStatus("Transcribed.");
            }
          } else if (data.type === "status" && data.state === "processing" && data.event === "nova_request_started") {
            setStatus("Thinking...");
          } else if (data.type === "status" && data.state === "idle" && data.event === "nova_request_done") {
            finalizePendingStop("server_done");
          } else if (data.type === "reply" && data.reply_text) {
            setStatus(data.reply_text);
            playReplyAudio(data.audio_url);
            finalizePendingStop("reply_received");
          } else if (data.type === "error" && data.message) {
            setStatus("Error: " + data.message);
            finalizePendingStop("error_received");
          }
        } catch (e) {
          /* non-JSON server messages ignored */
        }
      };
      streamClient.onReady = function () {
        voiceWsOpened = true;
        setStreamState("starting", "socket_open");
        setStatus("Listening…");
        streamClient
          .startCapture()
          .catch(function (err) {
            console.error("Nova capture error:", err);
            window.NOVA_STREAM_FAILED = true;
            var message = err && err.message ? err.message : "denied or unavailable";
            if (err && err.name === "NotAllowedError") {
              message = "microphone permission denied";
            } else if (err && err.name === "NotFoundError") {
              message = "no microphone device found";
            }
            setStatus("Microphone error: " + message);
            teardownStream();
          })
          .then(function () {
            if (streamClient) {
              setStreamState("recording", "capture_started");
            }
          });
      };
      streamClient.connect();
    } catch (err) {
      console.error("Nova connect error:", err);
      window.NOVA_STREAM_FAILED = true;
      setStatus("Connect failed.");
      teardownStream();
    }
  }

  function handleStopClick() {
    if (streamState === "idle" || streamState === "stopping") {
      console.info("[PTT] ignoring stop; state:", streamState);
      return;
    }
    setStreamState("stopping", "tap_stop");
    wsReplyPending = true;
    if (streamClient) {
      streamClient.requestStop();
    }
    setUiStreaming(false);
    setStatus("Stopping recording…");
    clearStopTimeout();
    stopTimeoutId = window.setTimeout(function () {
      if (wsReplyPending) {
        setStatus("Timed out waiting for server reply.");
        finalizePendingStop("timeout_waiting_reply");
      }
    }, NOVA_WS_REPLY_TIMEOUT_MS);
  }

  function handleMicToggleClick(e) {
    e.preventDefault();

    // PTT mode: first tap starts streaming; second tap stops and sends.
    if (streamState === "starting" || streamState === "recording") {
      // Currently recording: stop and send to backend.
      handleStopClick();
    } else {
      // Not recording yet: start.
      handleStartClick();
    }
  }

  if (useMicToggle && micToggleBtn) {
    micToggleBtn.addEventListener("click", handleMicToggleClick);
  }

  const useAjaxSubmit = form.getAttribute("data-nova-ajax-submit") === "true";
  if (useAjaxSubmit) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      const textInput = form.querySelector('input[name="text"]');
      const text = textInput && textInput.value ? textInput.value.trim() : "";
      if (!text) {
        setStatus("Enter a message to send.");
        return;
      }
      primeAudioPlaybackFromUserGesture();
      const url = form.getAttribute("action") || window.location.pathname;
      const fd = new FormData(form);
      textInput.value = "";
      setStatus("Sending…");
      postToUrl(url, fd)
        .then(function (resp) {
          return resp
            .json()
            .then(function (data) {
              return { ok: resp.ok, status: resp.status, data: data };
            })
            .catch(function () {
              return { ok: resp.ok, status: resp.status, data: { error: "Invalid response" } };
            });
        })
        .then(function (result) {
          if (!result.ok) {
            const errMsg =
              (result.data && result.data.error) || "Request failed (" + result.status + ")";
            setStatus(errMsg);
            return;
          }
          const reply = result.data.reply_text || "";
          setStatus(reply || "OK");
          const audioUrl = result.data.audio_url;
          playReplyAudio(audioUrl);
        })
        .catch(function (err) {
          console.error("Nova form submit error:", err);
          setStatus("Network error.");
        });
    });
  }

  // Expose sendToNova globally for other scripts (e.g., mission_focus.js)
  window.Nova = window.Nova || {};
  window.Nova.playReplyAudio = playReplyAudio;
  window.Nova.normalizeNovaAudioUrl = normalizeNovaAudioUrl;
  window.Nova.sendText = function (text) {
    if (!text || !text.trim()) {
      return;
    }
    primeAudioPlaybackFromUserGesture();
    const url = form.getAttribute("action") || "/api/nova/voice/";
    const fd = new FormData();
    fd.append("text", text.trim());
    const token = getCookie("csrftoken");
    const headers = { Accept: "application/json" };
    if (token) {
      headers["X-CSRFToken"] = token;
    }
    fetch(url, {
      method: "POST",
      headers: headers,
      body: fd,
      credentials: "same-origin",
    })
      .then(function (resp) {
        return resp
          .json()
          .then(function (data) {
            return { ok: resp.ok, status: resp.status, data: data };
          })
          .catch(function () {
            return { ok: resp.ok, status: resp.status, data: { error: "Invalid response" } };
          });
      })
      .then(function (result) {
        if (!result.ok) {
          var errMsg =
            (result.data && result.data.error) || "Request failed (" + result.status + ")";
          setStatus(errMsg);
          return;
        }
        var data = result.data;
        if (data && data.reply_text) {
          setStatus(data.reply_text);
        }
        playReplyAudio(data && data.audio_url);
      })
      .catch(function (err) {
        console.error("Nova.sendText error:", err);
        setStatus("Network error.");
      });
  };

  if (playReplyBtn) {
    playReplyBtn.addEventListener("click", function () {
      if (!lastReplyAudioUrl) {
        return;
      }
      primeAudioPlaybackFromUserGesture();
      var player = getReplyPlayer();
      player.src = lastReplyAudioUrl;
      player
        .play()
        .then(function () {
          setPlayReplyVisible(false);
        })
        .catch(function (err) {
          console.error("Nova manual play error:", err);
          setStatus("Could not play audio. Check the MP3 URL in the Network tab.");
        });
    });
  }

  window.addEventListener("pagehide", teardownStream);
  setUiStreaming(false);
})();
