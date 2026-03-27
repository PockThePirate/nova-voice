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

  let isListening = false;
  let wakeClient = null;
  let recognition = null;
  let isCapturing = false;

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
          // This gets called by NovaWakeEngine when Vosk detects "nova"
          console.log("[Wake] Wake event received");
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

    if (recognition) {
      try { recognition.stop(); } catch(e) {}
      recognition = null;
    }

    setStatus("Stopped");
  }

  function startSpeechCapture() {
    if (isCapturing) return;
    isCapturing = true;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setStatus("Speech API not available");
      isCapturing = false;
      return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onresult = function(event) {
      const transcript = event.results[0][0].transcript;
      setStatus('Heard: "' + transcript + '"');
      sendToNova(transcript);
      isCapturing = false;
    };

    recognition.onerror = function(event) {
      console.error("[Wake] Speech error:", event.error);
      setStatus("Error: " + event.error);
      isCapturing = false;
    };

    recognition.onend = function() {
      isCapturing = false;
      // Return to wake word listening
      setStatus("Wake word ready - say 'Nova'");
    };

    recognition.start();
  }

  function useSpeechFallback() {
    // Fallback: continuous listening with keyword spotting
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setStatus("Speech API not available");
      return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    let finalTranscript = "";

    recognition.onresult = function(event) {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          finalTranscript += result[0].transcript;
          const text = result[0].transcript.toLowerCase();
          if (text.includes("nova") || text.includes("hey nova")) {
            setStatus("Wake word detected!");
            // Extract command after wake word
            const parts = text.split(/nova|hey nova/i);
            if (parts[1] && parts[1].trim()) {
              sendToNova(parts[1].trim());
            }
          }
        } else {
          interim += result[0].transcript;
          if (interim.toLowerCase().includes("nova")) {
            setStatus("Heard: Nova...");
          }
        }
      }
    };

    recognition.onerror = function(event) {
      console.error("[Wake] Fallback error:", event.error);
      if (isListening) {
        // Restart on error
        setTimeout(function() {
          if (isListening && recognition) {
            recognition.start();
          }
        }, 1000);
      }
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
            new Audio(d.audio_url).play().catch(function (err) {
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

  console.log("[Wake] Nova wake word initialized");
})();