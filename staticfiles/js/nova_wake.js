(function () {
  "use strict";

  /**
   * NovaWakeClient with Vosk integration
   * 
   * Continuously listens for wake word "Nova" or "Hey Nova"
   * Once detected, captures audio for transcription and sends to Nova
   */

  const WAKE_BUTTON_ID = "nova-wake-btn";
  const STATUS_EL_ID = "nova-wake-status";

  const btn = document.getElementById(WAKE_BUTTON_ID);
  const statusEl = document.getElementById(STATUS_EL_ID);

  if (!btn) {
    // Wake-word UI is optional in PTT mode; exit silently when absent.
    return;
  }

  // Check for Vosk
  const hasVosk = typeof window.Vosk !== "undefined";
  const hasWakeEngine = typeof window.NovaWakeEngine !== "undefined";

  /** Longer pause before finalize; dulls intermittent TV/background STT churn. */
  const COMMAND_SILENCE_MS = 3750;
  const MAX_COMMAND_CAPTURE_MS = 30000;

  let isListening = false;
  let wakeClient = null;
  let recognition = null;
  let isCapturing = false;
  /** Debounce timers for Web Speech post-wake capture (Vosk path). */
  let wakeSpeechSilenceTimer = null;
  let wakeSpeechMaxTimer = null;
  /** Logs once per second while waiting for COMMAND_SILENCE_MS after last transcript change. */
  let wakeSilenceTickIntervalId = null;
  /** Debounce timers for fallback continuous recognition. */
  let fallbackSilenceTimer = null;
  let fallbackMaxTimer = null;
  let fallbackSilenceTickIntervalId = null;
  /** Second mic stream: energy-based end-of-command (see WakeCommandLevelMonitor). */
  let wakeLevelMonitor = null;

  function stopWakeLevelMonitor() {
    if (wakeLevelMonitor !== null) {
      try {
        wakeLevelMonitor.stop();
      } catch (e) {
        /* ignore */
      }
      wakeLevelMonitor = null;
    }
  }

  function clearWakeSilenceTick() {
    if (wakeSilenceTickIntervalId !== null) {
      clearInterval(wakeSilenceTickIntervalId);
      wakeSilenceTickIntervalId = null;
    }
  }

  function clearFallbackSilenceTick() {
    if (fallbackSilenceTickIntervalId !== null) {
      clearInterval(fallbackSilenceTickIntervalId);
      fallbackSilenceTickIntervalId = null;
    }
  }

  /**
   * Start 1s console logs counting silence since last meaningful transcript change.
   * @param {string} pathLabel e.g. "startSpeechCapture" or "useSpeechFallback"
   */
  function startSilenceSecondLogging(pathLabel) {
    clearWakeSilenceTick();
    clearFallbackSilenceTick();
    var secondsElapsed = 0;
    var thresholdS = COMMAND_SILENCE_MS / 1000;
    console.log(
      "[Wake] TRANSCRIPT silence timer: logging every 1s until",
      thresholdS,
      "s since last text change (" + pathLabel + ")"
    );
    var log = function () {
      secondsElapsed += 1;
      console.log(
        "[Wake] TRANSCRIPT silence:",
        secondsElapsed,
        "s /",
        thresholdS,
        "s (no STT change)"
      );
    };
    if (pathLabel === "useSpeechFallback") {
      fallbackSilenceTickIntervalId = setInterval(log, 1000);
    } else {
      wakeSilenceTickIntervalId = setInterval(log, 1000);
    }
  }

  function clearWakeSpeechTimers() {
    clearWakeSilenceTick();
    if (wakeSpeechSilenceTimer) {
      clearTimeout(wakeSpeechSilenceTimer);
      wakeSpeechSilenceTimer = null;
    }
    if (wakeSpeechMaxTimer) {
      clearTimeout(wakeSpeechMaxTimer);
      wakeSpeechMaxTimer = null;
    }
  }

  function clearFallbackTimers() {
    clearFallbackSilenceTick();
    if (fallbackSilenceTimer) {
      clearTimeout(fallbackSilenceTimer);
      fallbackSilenceTimer = null;
    }
    if (fallbackMaxTimer) {
      clearTimeout(fallbackMaxTimer);
      fallbackMaxTimer = null;
    }
  }

  /**
   * Normalize transcript for silence-timer dedupe (case/spacing jitter from background audio).
   * @param {string} s Raw transcript
   * @returns {string} Lowercase, collapsed whitespace, trimmed
   */
  function normalizeForSilenceCompare(s) {
    if (!s || typeof s !== "string") {
      return "";
    }
    return s.replace(/\s+/g, " ").trim().toLowerCase();
  }

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text;
    console.log("[Wake] Status:", text);
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
        modelPath: "/static/vosk/model-en/vosk-model-small-en-us-0.15.tar.gz",
        sampleRate: 16000,
        debug: true
      });

      // Set callback when wake word detected
      window.NovaWakeEngine.setOnWake(function() {
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
      // Start the wake client (continuous audio capture)
      wakeClient = new window.NovaWakeClient({
        onWake: function() {
          console.log("[Wake] Mic streaming to Vosk wake engine");
        }
      });
      await wakeClient.start();
    } else {
      // Fallback: use Web Speech API continuous mode
      useSpeechFallback();
    }
  }

  function stopListening() {
    if (!isListening) return;
    isListening = false;
    btn.classList.remove("recording");
    btn.innerHTML = "Nova\u003cbr\u003e🎙";

    if (wakeClient) {
      wakeClient.stop();
      wakeClient = null;
    }

    clearWakeSpeechTimers();
    clearFallbackTimers();
    stopWakeLevelMonitor();

    if (recognition) {
      try { recognition.stop(); } catch(e) {}
      recognition = null;
    }

    setStatus("Stopped");
  }

  function startSpeechCapture() {
    if (isCapturing) return;
    isCapturing = true;
    clearWakeSpeechTimers();

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setStatus("Speech API not available");
      isCapturing = false;
      return;
    }

    var speechFinalized = false;
    var lastFullText = "";
    /** Last text we used to (re)arm the silence timer — avoids reset loops from duplicate onresult. */
    var lastTextThatMovedSilenceTimer = "";

    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    function finalizeSpeechCapture() {
      if (speechFinalized) {
        return;
      }
      speechFinalized = true;
      stopWakeLevelMonitor();
      clearWakeSpeechTimers();
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
      if (!lastFullText) {
        return;
      }
      var fp = normalizeForSilenceCompare(lastFullText);
      if (!fp || fp === lastTextThatMovedSilenceTimer) {
        return;
      }
      lastTextThatMovedSilenceTimer = fp;
      var preview = lastFullText.length > 80 ? lastFullText.substring(0, 80) + "..." : lastFullText;
      setStatus('Heard: "' + preview + '"');
      if (wakeSpeechSilenceTimer) {
        clearTimeout(wakeSpeechSilenceTimer);
        wakeSpeechSilenceTimer = null;
      }
      startSilenceSecondLogging("startSpeechCapture");
      wakeSpeechSilenceTimer = setTimeout(finalizeSpeechCapture, COMMAND_SILENCE_MS);
    };

    recognition.onerror = function (event) {
      console.error("[Wake] Speech error:", event.error);
      setStatus("Error: " + event.error);
      speechFinalized = true;
      stopWakeLevelMonitor();
      clearWakeSpeechTimers();
      isCapturing = false;
    };

    recognition.onend = function () {
      if (speechFinalized) {
        setStatus("Wake word ready - say 'Nova'");
        return;
      }
      console.log(
        "[Wake] startSpeechCapture: recognition session ended; waiting for silence/max timer"
      );
    };

    wakeSpeechMaxTimer = setTimeout(finalizeSpeechCapture, MAX_COMMAND_CAPTURE_MS);

    stopWakeLevelMonitor();
    if (typeof window.WakeCommandLevelMonitor === "function") {
      wakeLevelMonitor = new window.WakeCommandLevelMonitor({
        calibrationMs: 320,
        silenceTimeoutMs: 2000,
        onLevelSilence: function () {
          finalizeSpeechCapture();
        },
      });
      wakeLevelMonitor
        .start()
        .then(function () {
          if (wakeLevelMonitor) {
            wakeLevelMonitor.beginCalibration();
          }
        })
        .catch(function (err) {
          console.warn("[Wake] Level monitor unavailable:", err);
          wakeLevelMonitor = null;
        });
    }

    recognition.start();
  }

  function useSpeechFallback() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setStatus("Speech API not available");
      return;
    }

    clearFallbackTimers();

    var fallbackAfterWake = false;
    var lastFull = "";
    var fallbackDone = false;
    /** Same as wake path: only re-arm silence when command text changes. */
    var lastCmdThatMovedSilenceTimer = "";

    /**
     * Return text after the last "(hey )?nova" in the phrase (command portion).
     * @param {string} s Full recognition string
     * @returns {string}
     */
    function extractAfterWake(s) {
      var m = s.match(/(?:hey\s+)?nova\s*(.*)$/i);
      if (!m) {
        return "";
      }
      return (m[1] || "").trim();
    }

    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    function finalizeFallback() {
      if (fallbackDone) {
        return;
      }
      fallbackDone = true;
      stopWakeLevelMonitor();
      clearFallbackTimers();
      try {
        recognition.stop();
      } catch (e) {
        /* ignore */
      }
      var cmd = extractAfterWake(lastFull);
      if (cmd) {
        setStatus('Heard: "' + cmd + '"');
        sendToNova(cmd);
      } else {
        setStatus("Wake word ready - say 'Nova'");
      }
    }

    recognition.onresult = function (event) {
      if (fallbackDone) {
        return;
      }
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
      var low = lastFull.toLowerCase();
      if (!fallbackAfterWake && (low.indexOf("nova") !== -1 || low.indexOf("hey nova") !== -1)) {
        fallbackAfterWake = true;
        lastCmdThatMovedSilenceTimer = "";
        setStatus("Wake word detected! Listening...");
        fallbackMaxTimer = setTimeout(finalizeFallback, MAX_COMMAND_CAPTURE_MS);

        stopWakeLevelMonitor();
        if (typeof window.WakeCommandLevelMonitor === "function") {
          wakeLevelMonitor = new window.WakeCommandLevelMonitor({
            calibrationMs: 320,
            silenceTimeoutMs: 2000,
            onLevelSilence: function () {
              finalizeFallback();
            },
          });
          wakeLevelMonitor
            .start()
            .then(function () {
              if (wakeLevelMonitor) {
                wakeLevelMonitor.beginCalibration();
              }
            })
            .catch(function (err) {
              console.warn("[Wake] Fallback level monitor unavailable:", err);
              wakeLevelMonitor = null;
            });
        }
      }
      if (!fallbackAfterWake) {
        return;
      }

      var cmd = extractAfterWake(lastFull);
      if (!cmd) {
        return;
      }
      var cmdFp = normalizeForSilenceCompare(cmd);
      if (!cmdFp || cmdFp === lastCmdThatMovedSilenceTimer) {
        return;
      }
      lastCmdThatMovedSilenceTimer = cmdFp;

      var preview = cmd.length > 80 ? cmd.substring(0, 80) + "..." : cmd;
      setStatus('Heard: "' + preview + '"');
      if (fallbackSilenceTimer) {
        clearTimeout(fallbackSilenceTimer);
        fallbackSilenceTimer = null;
      }
      startSilenceSecondLogging("useSpeechFallback");
      fallbackSilenceTimer = setTimeout(finalizeFallback, COMMAND_SILENCE_MS);
    };

    recognition.onerror = function (event) {
      console.error("[Wake] Fallback error:", event.error);
      stopWakeLevelMonitor();
      clearFallbackTimers();
      fallbackDone = false;
      fallbackAfterWake = false;
      lastFull = "";
      lastCmdThatMovedSilenceTimer = "";
      if (isListening) {
        setTimeout(function () {
          if (isListening && recognition) {
            try {
              recognition.start();
            } catch (e) {
              console.error("[Wake] Fallback restart error:", e);
            }
          }
        }, 1000);
      }
    };

    recognition.onend = function () {
      if (!isListening) {
        setStatus("Stopped");
        return;
      }
      if (!fallbackDone && (fallbackSilenceTimer != null || fallbackMaxTimer != null)) {
        console.log(
          "[Wake] useSpeechFallback: onend while silence/max pending; deferring restart"
        );
        return;
      }
      clearFallbackTimers();
      fallbackDone = false;
      fallbackAfterWake = false;
      lastFull = "";
      lastCmdThatMovedSilenceTimer = "";
      setTimeout(function () {
        if (isListening && recognition) {
          try {
            recognition.start();
          } catch (e) {
            console.error("[Wake] Fallback restart error:", e);
          }
        }
      }, 400);
    };

    recognition.start();
    setStatus("Listening for 'Nova'...");
  }

  function sendToNova(text) {
    if (!text || !text.trim()) return;
    setStatus('Sending: "' + text.substring(0, 30) + '..."');

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
        .then(r => r.json())
        .then(d => {
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
        .catch(e => {
          console.error("[Wake] Send error:", e);
          setStatus("Failed");
        });
    }
  }

  // Toggle button
  btn.addEventListener("click", function() {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  });

  console.log(
    "[Wake] Initialized: Wake button active — transcript + mic level timers log here when capturing a command"
  );
})();