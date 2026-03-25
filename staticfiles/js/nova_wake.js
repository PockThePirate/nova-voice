(function () {
  "use strict";

  /**
   * NovaWakeClient
   *
   * Front-end wake-listening scaffolding.
   *
   * For now this:
   * - Captures microphone audio continuously via ScriptProcessorNode
   * - Emits a `nova-wake` event on the first audio chunk (placeholder)
   * - Provides hooks for a future wake engine (e.g. Vosk WASM) via window.NovaWakeEngine
   */
  class NovaWakeClient {
    constructor(options) {
      const o = options || {};
      this.onWake = typeof o.onWake === "function" ? o.onWake : null;
      this._audioContext = null;
      this._mediaStream = null;
      this._processor = null;
      this._listening = false;
      this._hasWokenThisSession = false;
    }

    isListening() {
      return this._listening;
    }

    async start() {
      if (this._listening) return;
      this._listening = true;
      this._hasWokenThisSession = false;

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            channelCount: 1,
          },
          video: false,
        });
        this._mediaStream = stream;

        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        const ctx = new AudioCtx();
        this._audioContext = ctx;
        if (ctx.state === "suspended") {
          await ctx.resume();
        }

        const source = ctx.createMediaStreamSource(stream);
        const processor = ctx.createScriptProcessor(4096, 1, 1);
        this._processor = processor;

        const self = this;
        processor.onaudioprocess = function (event) {
          const input = event.inputBuffer.getChannelData(0);
          if (!input || !self._listening) return;

          // Hook for wake engine: pass Float32Array to Vosk or other engine
          var engineProcessed = false;
          if (window.NovaWakeEngine && typeof window.NovaWakeEngine.process === "function") {
            try {
              window.NovaWakeEngine.process(input);
              engineProcessed = true;
            } catch (e) {
              console.error("NovaWakeEngine.process error", e);
            }
          }

          // Fallback: if no engine present, fire wake on first non-silent audio
          if (!engineProcessed && !self._hasWokenThisSession && self._hasNonZeroSample(input)) {
            self._hasWokenThisSession = true;
            self._fireWake();
          }
        };

        source.connect(processor);
        processor.connect(ctx.destination); // required for some browsers
      } catch (err) {
        console.error("NovaWakeClient start error", err);
        this.stop();
        if (typeof window.NovaWakeOnError === "function") {
          try {
            window.NovaWakeOnError(err);
          } catch (_) {}
        }
      }
    }

    stop() {
      this._listening = false;

      if (this._processor) {
        try {
          this._processor.disconnect();
        } catch (_) {}
        this._processor.onaudioprocess = null;
        this._processor = null;
      }

      if (this._audioContext) {
        try {
          this._audioContext.close();
        } catch (_) {}
        this._audioContext = null;
      }

      if (this._mediaStream) {
        try {
          this._mediaStream.getTracks().forEach(function (t) {
            t.stop();
          });
        } catch (_) {}
        this._mediaStream = null;
      }
    }

    _hasNonZeroSample(buffer) {
      if (!buffer || buffer.length === 0) return false;
      for (let i = 0; i < buffer.length; i++) {
        const v = buffer[i];
        if (v > 1e-4 || v < -1e-4) return true;
      }
      return false;
    }

    _fireWake() {
      if (typeof this.onWake === "function") {
        try {
          this.onWake();
        } catch (e) {
          console.error("NovaWakeClient onWake error", e);
        }
      }
      try {
        const evt = new CustomEvent("nova-wake");
        window.dispatchEvent(evt);
      } catch (e) {
        // CustomEvent may not exist in very old browsers
      }
    }
  }

  window.NovaWakeClient = NovaWakeClient;
})();
