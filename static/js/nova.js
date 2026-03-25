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

  const MIC_LABEL_IDLE = "🎙 Wake Nova";
  const MIC_LABEL_ACTIVE = "⏹ Stop";

  const form = document.getElementById("nova-voice-form");
  if (!form) {
    return;
  }

  const statusEl = document.getElementById("nova-mic-status");

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

  const wsPath = form.getAttribute("data-nova-ws-path") || "/ws/audio/nova";
  const wsUrlAttr = form.getAttribute("data-nova-ws-url");
  const wsUrl =
    wsUrlAttr && (wsUrlAttr.indexOf("ws:") === 0 || wsUrlAttr.indexOf("wss:") === 0) ? wsUrlAttr : null;

  const startBtn =
    form.querySelector("[data-nova-stream-start]") || document.getElementById("nova-stream-start");
  const stopBtn =
    form.querySelector("[data-nova-stream-stop]") || document.getElementById("nova-stream-stop");
  const micToggleBtn = document.getElementById("nova-mic-btn");
  const useMicToggle = micToggleBtn && micToggleBtn.hasAttribute("data-nova-mic-toggle");

  // Wake-listening client (front-end only). Uses ScriptProcessorNode and can
  // be wired to a client-side wake engine (e.g. Vosk WASM) via NovaWakeEngine.
  let wakeClient = null;
  if (typeof window.NovaWakeClient === "function") {
    wakeClient = new window.NovaWakeClient({
      onWake: function () {
        // When wake word fires, start streaming if not already active.
        if (!streamClient) {
          handleStartClick();
        }
      },
    });
  }

  // Initialize Vosk wake engine if available and wire it into wakeClient
  if (window.NovaWakeEngine && typeof window.NovaWakeEngine.init === "function") {
    window.NovaWakeEngine
      .init({ debug: false })
      .then(function () {
        if (typeof window.NovaWakeEngine.setOnWake === "function" && wakeClient) {
          window.NovaWakeEngine.setOnWake(function () {
            if (wakeClient && typeof wakeClient.onWake === "function") {
              // Delegate to the same handler NovaWakeClient uses when it
              // detects wake locally (start streaming, etc.).
              wakeClient.onWake();
            }
          });
        }
      })
      .catch(function (err) {
        console.error("NovaWakeEngine init failed:", err);
      });
  }

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
    if (startBtn) {
      startBtn.disabled = streaming;
    }
    if (stopBtn) {
      stopBtn.disabled = !streaming;
    }
    if (useMicToggle && micToggleBtn) {
      micToggleBtn.disabled = false;
      micToggleBtn.textContent = streaming ? MIC_LABEL_ACTIVE : MIC_LABEL_IDLE;
    }
  }

  function teardownStream() {
    if (streamClient) {
      streamClient.disconnect();
      streamClient = null;
    }
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
    if (!canUseStream()) {
      window.NOVA_STREAM_FAILED = true;
      setStatus("Voice stream unavailable (WebSocket client not loaded).");
      return;
    }
    setUiStreaming(true);
    setStatus("Connecting…");
    let voiceWsOpened = false;
    try {
      streamClient = new window.NovaStreamClient(wsUrl ? { wsUrl: wsUrl } : { path: wsPath });
      streamClient.onConnectionLost = function (ev) {
        streamClient = null;
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
      // When the user stops speaking for ~2 seconds, treat it as end of
      // utterance and stop the stream. This will transition the status to
      // "Query sent…" via handleStopClick().
      streamClient.onSilence = function () {
        handleStopClick();
      };
      streamClient.onMessage = function (event) {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "status" && data.state === "listening") {
            setStatus("Listening…");
          } else if (data.type === "reply" && data.reply_text) {
            setStatus(data.reply_text);
          } else if (data.type === "error" && data.message) {
            setStatus("Error: " + data.message);
          }
        } catch (e) {
          /* non-JSON server messages ignored */
        }
      };
      streamClient.onReady = function () {
        voiceWsOpened = true;
        setStatus("Listening…");
        streamClient
          .startCapture()
          .catch(function (err) {
            console.error("Nova capture error:", err);
            window.NOVA_STREAM_FAILED = true;
            setStatus("Microphone error: " + (err && err.message ? err.message : "denied or unavailable"));
            teardownStream();
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
    if (streamClient) {
      streamClient.disconnect();
      streamClient = null;
    }
    setUiStreaming(false);
    // User has finished speaking; indicate that the query is on its way
    // to Nova before a reply is available.
    setStatus("Query sent…");
  }

  function handleMicToggleClick(e) {
    e.preventDefault();

    // Wake mode: mic button controls continuous wake listening; actual
    // conversation streaming starts when the wake client fires.
    if (wakeClient) {
      if (wakeClient.isListening()) {
        // Stop wake listening and any active stream.
        wakeClient.stop();
        if (streamClient) {
          handleStopClick();
        } else {
          setUiStreaming(false);
          setStatus("");
        }
      } else {
        // Start wake listening; wakeClient.onWake will start streaming.
        wakeClient.start();
        if (useMicToggle && micToggleBtn) {
          micToggleBtn.disabled = false;
          micToggleBtn.textContent = MIC_LABEL_ACTIVE;
        }
        setStatus("Listening for wake word…");
      }
      return;
    }

    // Fallback: original push-to-talk behavior if wakeClient is unavailable.
    if (streamClient) {
      handleStopClick();
    } else {
      handleStartClick();
    }
  }

  if (startBtn) {
    startBtn.addEventListener("click", function (e) {
      e.preventDefault();
      handleStartClick();
    });
  }
  if (stopBtn) {
    stopBtn.addEventListener("click", function (e) {
      e.preventDefault();
      handleStopClick();
    });
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
          if (audioUrl) {
            const player = new Audio(audioUrl);
            player.play().catch(function (playErr) {
              console.error("Nova audio play error:", playErr);
              setStatus(reply + " (audio playback blocked)");
            });
          }
        })
        .catch(function (err) {
          console.error("Nova form submit error:", err);
          setStatus("Network error.");
        });
    });
  }

  // Expose sendToNova globally for other scripts (e.g., mission_focus.js)
  window.Nova = window.Nova || {};
  window.Nova.sendText = function (text) {
    if (!text || !text.trim()) return;
    const url = form.getAttribute("action") || "/api/nova/voice/";
    const fd = new FormData();
    fd.append("text", text.trim());
    const token = getCookie("csrftoken");
    fetch(url, {
      method: "POST",
      headers: token ? { "X-CSRFToken": token } : {},
      body: fd,
      credentials: "same-origin",
    })
      .then(function (resp) {
        return resp.json().catch(function () {
          return { error: "Invalid response" };
        });
      })
      .then(function (data) {
        if (data && data.audio_url) {
          const player = new Audio(data.audio_url);
          player.play().catch(function () {});
        }
      })
      .catch(function (err) {
        console.error("Nova.sendText error:", err);
      });
  };

  window.addEventListener("pagehide", teardownStream);
  setUiStreaming(false);
})();
