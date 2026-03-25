(function () {
  "use strict";

  /**
   * Push-to-talk voice input for Nova.
   * 
   * Hold the round button to record audio.
   * Release to stop recording and transcribe.
   * 
   * Uses Web Speech API for transcription (browser built-in).
   * Falls back to no transcription if not available.
   */

  const PTT_BUTTON_ID = "nova-ptt-btn";
  const STATUS_EL_ID = "nova-ptt-status";

  const btn = document.getElementById(PTT_BUTTON_ID);
  if (!btn) {
    console.log("[PTT] Button not found, skipping init");
    return;
  }

  // Check for Web Speech API support
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const hasSpeechAPI = !!SpeechRecognition;

  let recognition = null;
  let isRecording = false;

  function setStatus(text) {
    const el = document.getElementById(STATUS_EL_ID);
    if (el) {
      el.textContent = text;
    }
  }

  function startRecording() {
    if (isRecording) return;
    
    isRecording = true;
    btn.classList.add("recording");
    btn.innerHTML = "Listening<br>...";
    setStatus("Speak now...");

    if (!hasSpeechAPI) {
      setStatus("Speech API not available");
      return;
    }

    try {
      recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = "en-US";

      recognition.onresult = function (event) {
        const transcript = event.results[0][0].transcript;
        setStatus('Heard: "' + transcript + '"');
        sendToNova(transcript);
      };

      recognition.onerror = function (event) {
        console.error("[PTT] Speech error:", event.error);
        setStatus("Error: " + event.error);
        stopRecording();
      };

      recognition.onend = function () {
        stopRecording();
      };

      recognition.start();
    } catch (err) {
      console.error("[PTT] Failed:", err);
      setStatus("Mic access denied");
      stopRecording();
    }
  }

  function stopRecording() {
    if (!isRecording) return;
    
    isRecording = false;
    btn.classList.remove("recording");
    btn.innerHTML = "Nova<br>🎙";

    if (recognition) {
      try {
        recognition.stop();
      } catch (e) {}
      recognition = null;
    }

    setStatus("Processing...");
  }

  function sendToNova(text) {
    if (!text || !text.trim()) {
      setStatus("No speech detected");
      return;
    }

    setStatus('Sending: "' + text.trim().substring(0, 30) + '..."');

    // Use existing Nova.sendText if available
    if (window.Nova && typeof window.Nova.sendText === "function") {
      window.Nova.sendText(text.trim());
      setStatus("Sent to Nova");
    } else {
      // Fallback: POST to voice API
      const form = document.getElementById("nova-voice-form");
      const url = form ? form.getAttribute("action") : "/api/nova/voice/";
      
      const fd = new FormData();
      fd.append("text", text.trim());
      
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

      fetch(url, {
        method: "POST",
        headers: getCookie("csrftoken") ? { "X-CSRFToken": getCookie("csrftoken") } : {},
        body: fd,
        credentials: "same-origin",
      })
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
          if (data.audio_url) {
            new Audio(data.audio_url).play().catch(function(){});
            setStatus("Nova replied");
          } else {
            setStatus("No response");
          }
        })
        .catch(function (err) {
          console.error("[PTT] Send error:", err);
          setStatus("Failed");
        });
    }
  }

  // Mouse events
  btn.addEventListener("mousedown", function (e) {
    e.preventDefault();
    startRecording();
  });

  btn.addEventListener("mouseup", function (e) {
    e.preventDefault();
    stopRecording();
  });

  btn.addEventListener("mouseleave", function (e) {
    if (isRecording) stopRecording();
  });

  // Touch events for mobile
  btn.addEventListener("touchstart", function (e) {
    e.preventDefault();
    startRecording();
  });

  btn.addEventListener("touchend", function (e) {
    e.preventDefault();
    stopRecording();
  });

  console.log("[PTT] Push-to-talk ready");
})();
