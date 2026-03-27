(function () {
  "use strict";

  /**
   * Toggle voice input for Nova.
   * 
   * Click to start recording, click again to stop and transcribe.
   * Works on mobile and desktop.
   */

  const PTT_BUTTON_ID = "nova-ptt-btn";
  const STATUS_EL_ID = "nova-ptt-status";

  const btn = document.getElementById(PTT_BUTTON_ID);
  const statusEl = document.getElementById(STATUS_EL_ID);

  if (!btn) {
    console.log("[Voice] Button not found");
    return;
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const hasSpeechAPI = !!SpeechRecognition;

  let recognition = null;
  let isRecording = false;
  let transcript = "";

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text;
  }

  function startRecording() {
    if (!hasSpeechAPI) {
      setStatus("Speech API not available");
      return;
    }

    transcript = "";
    
    try {
      recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      recognition.onstart = function() {
        isRecording = true;
        btn.classList.add("recording");
        btn.innerHTML = "⏹\u003cbr\u003eStop";
        setStatus("Listening... speak now");
      };

      recognition.onresult = function(event) {
        let finalTranscript = "";
        let interimTranscript = "";

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i];
          if (result.isFinal) {
            finalTranscript += result[0].transcript;
          } else {
            interimTranscript += result[0].transcript;
          }
        }

        if (finalTranscript) {
          transcript += finalTranscript;
        }

        setStatus('Heard: "' + (transcript || interimTranscript) + '"');
      };

      recognition.onerror = function(event) {
        console.error("[Voice] Error:", event.error);
        if (event.error !== "aborted") {
          setStatus("Error: " + event.error);
        }
        stopRecording();
      };

      recognition.onend = function() {
        // Only auto-restart if we're still in recording mode (user hasn't clicked stop)
        if (isRecording) {
          try {
            recognition.start();
          } catch (e) {
            stopRecording();
          }
        }
      };

      recognition.start();
    } catch (err) {
      console.error("[Voice] Start failed:", err);
      setStatus("Mic access denied");
      stopRecording();
    }
  }

  function stopRecording() {
    isRecording = false;
    btn.classList.remove("recording");
    btn.innerHTML = "🎙\u003cbr\u003eNova";

    if (recognition) {
      try {
        recognition.stop();
      } catch (e) {}
      recognition = null;
    }

    // Send the transcript
    if (transcript.trim()) {
      sendToNova(transcript.trim());
    } else {
      setStatus("No speech detected");
    }
  }

  function toggleRecording() {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  }

  function sendToNova(text) {
    setStatus('Sending: "' + text.substring(0, 40) + '..."');

    if (window.Nova && typeof window.Nova.sendText === "function") {
      window.Nova.sendText(text);
      setStatus("Sent to Nova");
    } else {
      // Fallback POST
      const form = document.getElementById("nova-voice-form");
      const url = form ? form.getAttribute("action") : "/api/nova/voice/";
      
      const fd = new FormData();
      fd.append("text", text);
      
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
          } else if (d.audio_url) {
            setStatus("Nova replied");
          } else {
            setStatus("Sent");
          }
          if (d.audio_url && window.Nova && typeof window.Nova.playReplyAudio === "function") {
            window.Nova.playReplyAudio(d.audio_url);
          } else if (d.audio_url) {
            new Audio(d.audio_url).play().catch(function (err) {
              console.error("[Voice] Nova audio play error:", err);
            });
          }
        })
        .catch(e => {
          console.error("[Voice] Send error:", e);
          setStatus("Failed to send");
        });
    }
  }

  // Toggle on click
  btn.addEventListener("click", function(e) {
    e.preventDefault();
    toggleRecording();
  });

  // Touch support for mobile
  btn.addEventListener("touchstart", function(e) {
    e.preventDefault();
  });

  console.log("[Voice] Toggle mode initialized");
})();
