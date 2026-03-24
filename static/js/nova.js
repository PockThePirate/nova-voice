(function () {
  const form = document.getElementById("nova-voice-form");
  if (!form) return;

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

  const useStream = false; // fallback to HTTP backend for Nova (stable on mobile)
  let streamClient = null;

  async function sendToNova(text) {
    if (!text.trim()) return;

    if (useStream && window.NovaStreamClient) {
      if (!streamClient) {
        streamClient = new window.NovaStreamClient();
        streamClient.connect();
      }
      streamClient.sendDebugCommand(text);
      return;
    }

    const csrftoken = getCookie("csrftoken");
    try {
      const res = await fetch("/api/nova/voice/", {
        method: "POST",
        headers: {
          "X-CSRFToken": csrftoken,
        },
        body: new URLSearchParams({ text }),
      });
      const data = await res.json();
      if (data.audio_url) {
        const audio = new Audio(data.audio_url);
        audio.play().catch(() => {});
      }
    } catch (err) {
      console.error("Nova voice error", err);
    }
  }

  // Text submit
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = form.querySelector("input[name='text']");
    if (!input || !input.value.trim()) return;
    const text = input.value.trim();
    input.value = "";
    await sendToNova(text);
  });

  // Wake‑word mic (push‑to‑talk via browser speech recognition)
  const micBtn = document.getElementById("nova-mic-btn");
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition && micBtn) {
    micBtn.disabled = true;
    micBtn.title = "Speech recognition not supported in this browser";
  }

  if (SpeechRecognition && micBtn) {
    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.continuous = false; // single sessions we restart manually
    recognition.interimResults = false;

    let listening = false;          // overall on/off
    let awaitingCommand = false;    // we heard "Nova" / "Hey Nova" and are capturing the command
    let silenceTimer = null;        // fires 2s after last chunk once wake word heard
    let pendingCommand = "";       // accumulated command text after wake word
    let sessionStart = 0;           // when this listening session began

    const statusEl = document.getElementById("nova-mic-status");

    function setStatus(text) {
      if (!statusEl) return;
      statusEl.textContent = text;
    }

    function resetButton() {
      micBtn.classList.remove("listening");
      micBtn.textContent = "🎙 Wake Nova";
      listening = false;
      awaitingCommand = false;
      pendingCommand = "";
      if (silenceTimer) {
        clearTimeout(silenceTimer);
        silenceTimer = null;
      }
      setStatus("");
    }

    function scheduleCommand() {
      if (silenceTimer) {
        clearTimeout(silenceTimer);
        silenceTimer = null;
      }
      if (!pendingCommand.trim()) return;
      // Wait 2 seconds after the last recognized chunk before firing
      silenceTimer = setTimeout(async () => {
        const toSend = pendingCommand.trim();
        pendingCommand = "";
        awaitingCommand = false;
        setStatus("Processing command…");
        await sendToNova(toSend);
        // After response, go back to listening for the wake word until the 2‑minute window ends
        setStatus("Listening for \"Nova\"…");
      }, 2000);
    }

    recognition.addEventListener("result", (event) => {
      if (!event.results || event.results.length === 0) return;
      const result = event.results[event.results.length - 1];
      if (!result || result.length === 0) return;
      const transcriptRaw = result[0].transcript;
      const transcript = transcriptRaw.trim();
      if (!transcript) return;

      const lowered = transcript.toLowerCase();
      const hasWake = lowered.includes("hey nova") || lowered.includes("nova");

      if (hasWake && !awaitingCommand) {
        awaitingCommand = true;
        pendingCommand = ""; // start fresh after wake word
        setStatus("Heard \"Nova\" – listening for command…");
      }

      if (awaitingCommand) {
        // Strip the wake word out of the transcript and append the remainder.
        let clean = transcript;
        const idxHey = lowered.indexOf("hey nova");
        const idxNova = lowered.indexOf("nova");
        let idx = -1;
        if (idxHey !== -1) idx = idxHey + "hey nova".length;
        else if (idxNova !== -1) idx = idxNova + "nova".length;
        if (idx !== -1) {
          clean = transcriptRaw.slice(idx).trim();
        }
        if (clean) {
          pendingCommand = (pendingCommand + " " + clean).trim();
        }
        // Each new chunk after wake word resets the 2s silence timer
        scheduleCommand();
      }
    });

    recognition.addEventListener("end", () => {
      if (!listening) return;

      const elapsed = Date.now() - sessionStart;
      // Stop automatically after 2 minutes
      if (elapsed >= 120000) {
        resetButton();
        return;
      }

      try {
        recognition.start();
      } catch (e) {
        console.error("Nova mic restart error", e);
        resetButton();
      }
    });

    recognition.addEventListener("error", () => {
      resetButton();
    });

    micBtn.addEventListener("click", () => {
      // Second tap: turn off listening entirely
      if (listening) {
        listening = false;
        try { recognition.stop(); } catch (e) {}
        resetButton();
        return;
      }

      // First tap: start a 2‑minute listening window
      try {
        listening = true;
        awaitingCommand = false;
        pendingCommand = "";
        sessionStart = Date.now();
        micBtn.classList.add("listening");
        micBtn.textContent = "Listening…";
        setStatus("Listening for \"Nova\"…");
        recognition.start();
      } catch (e) {
        console.error("Nova mic start error", e);
        resetButton();
      }
    });
  }
})();
