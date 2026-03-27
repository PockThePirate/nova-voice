(function () {
  "use strict";

  /**
   * NovaWakeClient with Vosk integration
   *
   * Continuously listens for wake word "Nova" or "Hey Nova"
   * Once detected, captures one browser utterance (Web Speech end-of-speech)
   * and sends the transcript to Nova.
   */

  const WAKE_BUTTON_ID = "nova-wake-btn";
  const STATUS_EL_ID = "nova-wake-status";
  /** Applied while an HTTP voice request is in flight (until JSON + audio URL return). */
  const WAKE_WAITING_AUDIO_CLASS = "nova-wake-waiting-audio";

  const btn = document.getElementById(WAKE_BUTTON_ID);
  const statusEl = document.getElementById(STATUS_EL_ID);

  if (!btn) {
    // Wake-word UI is optional in PTT mode; exit silently when absent.
    return;
  }

  // Check for Vosk
  const hasVosk = typeof window.Vosk !== "undefined";
  const hasWakeEngine = typeof window.NovaWakeEngine !== "undefined";

  /** Safety cap if the speech engine never fires onend. */
  const MAX_COMMAND_CAPTURE_MS = 30000;

  let isListening = false;
  let wakeClient = null;
  let recognition = null;
  let isCapturing = false;
  let wakeSpeechMaxTimer = null;
  let fallbackMaxTimer = null;

  /**
   * Toggle yellow “waiting for Nova audio” on the wake button.
   *
   * @param {boolean} active Whether the voice API request is in flight
   * @returns {void}
   *
   * @example
   * setWakeWaitingAudio(true);
   */
  function setWakeWaitingAudio(active) {
    if (!btn) {
      return;
    }
    btn.classList.toggle(WAKE_WAITING_AUDIO_CLASS, !!active);
  }

  function clearWakeSpeechMaxTimer() {
    if (wakeSpeechMaxTimer) {
      clearTimeout(wakeSpeechMaxTimer);
      wakeSpeechMaxTimer = null;
    }
  }

  function clearFallbackMaxTimer() {
    if (fallbackMaxTimer) {
      clearTimeout(fallbackMaxTimer);
      fallbackMaxTimer = null;
    }
  }

  function setStatus(text) {
    if (statusEl) {
      statusEl.textContent = text;
    }
  }

  async function initVoskWake() {
    if (!hasVosk || !hasWakeEngine) {
      setStatus("Vosk not loaded - using fallback");
      return false;
    }

    try {
      setStatus("Loading wake word engine...");
      await window.NovaWakeEngine.init({
        wakePhrases: ["nova", "hey nova"],
        modelPath:
          "/static/vosk/model-en/vosk-model-small-en-us-0.15.tar.gz?v=wake20260329",
        sampleRate: 16000,
        debug: false
      });

      // Set callback when wake word detected
      window.NovaWakeEngine.setOnWake(function () {
        setStatus("Wake word detected! Listening...");
        startSpeechCapture();
      });

      setStatus("Wake word ready - say 'Nova' or 'Hey Nova'");
      return true;
    } catch (err) {
      console.error("[Wake] Vosk init error:", err);
      setStatus("Wake word failed - using fallback");
      return false;
    }
  }

  async function startListening() {
    if (isListening) return;
    isListening = true;
    btn.classList.add("recording");
    btn.innerHTML = "👂\u003cbr\u003eListening";

    const voskReady = await initVoskWake();

    if (voskReady) {
      wakeClient = new window.NovaWakeClient({});
      try {
        await wakeClient.start();
        console.info(
          "[Wake] Mic streaming to Vosk (echo/noise DSP off for sensitivity)."
        );
      } catch (micErr) {
        console.error("[Wake] Mic start failed after Vosk init:", micErr);
        setStatus("Mic blocked — check permission or close other mic uses");
        isListening = false;
        btn.classList.remove("recording");
        btn.innerHTML = "\ud83d\udc42\u003cbr\u003eWake";
        wakeClient = null;
        return;
      }
    } else {
      useSpeechFallback();
    }
  }

  function stopListening() {
    if (!isListening) return;
    isListening = false;
    btn.classList.remove("recording");
    btn.classList.remove(WAKE_WAITING_AUDIO_CLASS);
    btn.innerHTML = "\ud83d\udc42\u003cbr\u003eWake";

    if (wakeClient) {
      wakeClient.stop();
      wakeClient = null;
    }

    clearWakeSpeechMaxTimer();
    clearFallbackMaxTimer();

    if (recognition) {
      try {
        recognition.stop();
      } catch (e) {}
      recognition = null;
    }

    setStatus("Stopped");
  }

  /**
   * After Vosk wake: one Web Speech session with continuous=false so the
   * browser ends the session on its own silence / end-of-utterance rules.
   *
   * @returns {void}
   *
   * @example
   * // Invoked from NovaWakeEngine.setOnWake
   * startSpeechCapture();
   */
  function startSpeechCapture() {
    if (isCapturing) return;
    isCapturing = true;
    clearWakeSpeechMaxTimer();

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setStatus("Speech API not available");
      isCapturing = false;
      return;
    }

    var speechFinalized = false;
    var lastFullText = "";

    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    function finalizeSpeechCapture() {
      if (speechFinalized) {
        return;
      }
      speechFinalized = true;
      clearWakeSpeechMaxTimer();
      try {
        recognition.stop();
      } catch (e) {
        /* ignore */
      }
      isCapturing = false;
      var t = lastFullText.trim();
      if (t) {
        setStatus('Heard: "' + t + '"');
        sendToNova(t);
      } else {
        setStatus("Wake word ready - say 'Nova'");
      }
    }

    recognition.onresult = function (event) {
      var fullFinal = "";
      var inter = "";
      var i;
      for (i = 0; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          fullFinal += event.results[i][0].transcript;
        } else {
          inter += event.results[i][0].transcript;
        }
      }
      lastFullText = (fullFinal + inter).trim();
      if (lastFullText) {
        var preview =
          lastFullText.length > 80 ? lastFullText.substring(0, 80) + "..." : lastFullText;
        setStatus('Heard: "' + preview + '"');
      }
    };

    recognition.onerror = function (event) {
      console.error("[Wake] Speech error:", event.error);
      setStatus("Error: " + event.error);
      speechFinalized = true;
      clearWakeSpeechMaxTimer();
      isCapturing = false;
    };

    recognition.onend = function () {
      if (speechFinalized) {
        setStatus("Wake word ready - say 'Nova'");
        return;
      }
      finalizeSpeechCapture();
    };

    wakeSpeechMaxTimer = setTimeout(finalizeSpeechCapture, MAX_COMMAND_CAPTURE_MS);

    try {
      recognition.start();
    } catch (e) {
      console.error("[Wake] Command capture start error:", e);
      clearWakeSpeechMaxTimer();
      isCapturing = false;
      setStatus("Speech start failed");
    }
  }

  /**
   * Return text after the last "(hey )?nova" in the phrase (command portion).
   *
   * @param {string} s Full recognition string
   * @returns {string} Trailing command text or empty string
   *
   * @example
   * extractAfterWake("hey nova what time"); // "what time"
   */
  function extractAfterWake(s) {
    var m = s.match(/(?:hey\s+)?nova\s*(.*)$/i);
    if (!m) {
      return "";
    }
    return (m[1] || "").trim();
  }

  /**
   * No Vosk: listen in short non-continuous sessions so each phrase uses the
   * browser’s end-of-utterance cutoff; loop while isListening.
   *
   * @returns {void}
   *
   * @example
   * useSpeechFallback();
   */
  function useSpeechFallback() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setStatus("Speech API not available");
      return;
    }

    function listenOneFallbackUtterance() {
      if (!isListening) {
        return;
      }
      clearFallbackMaxTimer();

      var lastFull = "";
      var cycleFinished = false;

      function completeCycle() {
        if (!isListening) {
          return;
        }
        if (cycleFinished) {
          return;
        }
        cycleFinished = true;
        clearFallbackMaxTimer();
        var low = lastFull.toLowerCase();
        if (low.indexOf("nova") !== -1 || low.indexOf("hey nova") !== -1) {
          var cmd = extractAfterWake(lastFull);
          if (cmd) {
            setStatus('Heard: "' + cmd + '"');
            sendToNova(cmd);
          } else {
            setStatus("Wake word ready - say 'Nova' and your request");
          }
        }
        setTimeout(listenOneFallbackUtterance, 450);
      }

      recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      recognition.onresult = function (event) {
        var fullFinal = "";
        var inter = "";
        var i;
        for (i = 0; i < event.results.length; i++) {
          if (event.results[i].isFinal) {
            fullFinal += event.results[i][0].transcript;
          } else {
            inter += event.results[i][0].transcript;
          }
        }
        lastFull = (fullFinal + inter).trim();
        if (lastFull) {
          var preview = lastFull.length > 80 ? lastFull.substring(0, 80) + "..." : lastFull;
          setStatus('Heard: "' + preview + '"');
        }
      };

      recognition.onerror = function (event) {
        console.error("[Wake] Fallback error:", event.error);
        clearFallbackMaxTimer();
        /* onend usually follows; completeCycle runs once there. */
      };

      recognition.onend = function () {
        if (!isListening) {
          setStatus("Stopped");
          return;
        }
        completeCycle();
      };

      fallbackMaxTimer = setTimeout(function () {
        try {
          recognition.stop();
        } catch (e2) {
          /* ignore */
        }
      }, MAX_COMMAND_CAPTURE_MS);

      try {
        recognition.start();
      } catch (e) {
        console.error("[Wake] Fallback start error:", e);
        clearFallbackMaxTimer();
        setTimeout(listenOneFallbackUtterance, 600);
        return;
      }
      setStatus("Listening for 'Nova'...");
    }

    listenOneFallbackUtterance();
  }

  function sendToNova(text) {
    if (!text || !text.trim()) {
      return;
    }
    setStatus('Sending: "' + text.substring(0, 30) + '..."');
    setWakeWaitingAudio(true);

    if (window.Nova && typeof window.Nova.sendText === "function") {
      window.Nova.sendText(text.trim());
    } else {
      // Direct POST fallback
      const form = document.getElementById("nova-voice-form");
      const url = form ? form.getAttribute("action") : "/api/nova/voice/";

      const fd = new FormData();
      fd.append("text", text.trim());

      function getCookie(name) {
        let v = null;
        if (document.cookie) {
          const c = document.cookie.split(";");
          for (let i = 0; i < c.length; i++) {
            const x = c[i].trim();
            if (x.indexOf(name + "=") === 0) {
              v = decodeURIComponent(x.substring(name.length + 1));
            }
          }
        }
        return v;
      }

      fetch(url, {
        method: "POST",
        headers: getCookie("csrftoken") ? { "X-CSRFToken": getCookie("csrftoken") } : {},
        body: fd,
        credentials: "same-origin",
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (d) {
          if (d.reply_text) {
            setStatus(d.reply_text);
          } else {
            setStatus("Nova replied");
          }
          if (d.audio_url && window.Nova && typeof window.Nova.playReplyAudio === "function") {
            window.Nova.playReplyAudio(d.audio_url);
          } else if (d.audio_url) {
            var _u = d.audio_url;
            if (window.Nova && typeof window.Nova.normalizeNovaAudioUrl === "function") {
              _u = window.Nova.normalizeNovaAudioUrl(_u);
            }
            new Audio(_u).play().catch(function (err) {
              console.error("[Wake] Nova audio play error:", err);
            });
          }
        })
        .catch(function (e) {
          console.error("[Wake] Send error:", e);
          setStatus("Failed");
        })
        .then(
          function notifyWakeFetchOk(value) {
            if (typeof window.Nova._notifyWakeReplyDone === "function") {
              try {
                window.Nova._notifyWakeReplyDone();
              } catch (e2) {
                /* ignore */
              }
            } else {
              setWakeWaitingAudio(false);
            }
            return value;
          },
          function notifyWakeFetchErr(reason) {
            if (typeof window.Nova._notifyWakeReplyDone === "function") {
              try {
                window.Nova._notifyWakeReplyDone();
              } catch (e2) {
                /* ignore */
              }
            } else {
              setWakeWaitingAudio(false);
            }
            throw reason;
          }
        );
    }
  }

  window.Nova = window.Nova || {};
  window.Nova._notifyWakeReplyDone = function () {
    setWakeWaitingAudio(false);
  };

  // Toggle button
  btn.addEventListener("click", function () {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  });
})();
