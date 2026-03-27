/**
 * Mic capture for browser Vosk wake: resample to 16 kHz and call NovaWakeEngine.process.
 */
(function () {
  "use strict";

  /**
   * @param {Int16Array} int16 PCM int16 samples
   * @returns {Float32Array} Normalized float [-1,1]
   */
  function int16ToFloat32(int16) {
    var f = new Float32Array(int16.length);
    var i;
    for (i = 0; i < int16.length; i++) {
      f[i] = int16[i] / 32768.0;
    }
    return f;
  }

  /**
   * Downsample float mono PCM (duplicates NovaStreamClient logic if class unavailable).
   *
   * @param {Float32Array} input
   * @param {number} inputRate
   * @param {number} outputRate
   * @returns {Int16Array}
   */
  function downsampleToInt16(input, inputRate, outputRate) {
    if (!input || input.length === 0) {
      return new Int16Array(0);
    }
    if (outputRate >= inputRate) {
      return floatToInt16(input);
    }
    var ratio = inputRate / outputRate;
    var outLength = Math.max(1, Math.floor(input.length / ratio));
    var out = new Int16Array(outLength);
    var pos = 0;
    var i;
    var s;
    for (i = 0; i < outLength; i++) {
      var srcIndex = Math.min(input.length - 1, Math.floor(pos));
      s = input[srcIndex];
      if (s > 1) {
        s = 1;
      } else if (s < -1) {
        s = -1;
      }
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      pos += ratio;
    }
    return out;
  }

  /**
   * @param {Float32Array} input
   * @returns {Int16Array}
   */
  function floatToInt16(input) {
    var out = new Int16Array(input.length);
    var i;
    var s;
    for (i = 0; i < input.length; i++) {
      s = input[i];
      if (s > 1) {
        s = 1;
      } else if (s < -1) {
        s = -1;
      }
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }

  /**
   * Feed the Vosk wake engine from the microphone.
   *
   * General purpose: after NovaWakeEngine.init and setOnWake, call start() to open the mic;
   * partial/final results that match wake phrases invoke the engine callback.
   *
   * @param {Object} [options]
   * @param {function(): void} [options.onWake] Optional log hook when mic starts (not phrase detection).
   * @param {number} [options.targetSampleRate=16000] Must match KaldiRecognizer sample rate.
   * @param {number} [options.bufferSize=4096] ScriptProcessor buffer size (power of two).
   *
   * @example
   * var client = new NovaWakeClient({ onWake: function () { console.log("mic on"); } });
   * await client.start();
   */
  function NovaWakeClient(options) {
    var o = options || {};
    this._onWake = typeof o.onWake === "function" ? o.onWake : null;
    this._targetSampleRate =
      typeof o.targetSampleRate === "number" ? o.targetSampleRate : 16000;
    this._bufferSize = typeof o.bufferSize === "number" ? o.bufferSize : 4096;
    this._mediaStream = null;
    this._audioContext = null;
    this._processor = null;
    this._source = null;
    this._mute = null;
    this._running = false;
  }

  /**
   * Open mic and stream 16 kHz-equivalent float frames to NovaWakeEngine.process.
   *
   * @returns {Promise<void>}
   */
  NovaWakeClient.prototype.start = function start() {
    var self = this;
    if (this._running) {
      return Promise.resolve();
    }
    return navigator.mediaDevices
      .getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          channelCount: 1,
        },
        video: false,
      })
      .then(function (stream) {
        self._mediaStream = stream;
        var AudioCtx = window.AudioContext || window.webkitAudioContext;
        self._audioContext = new AudioCtx();
        var ctx = self._audioContext;
        if (ctx.state === "suspended") {
          return ctx.resume().then(function () {
            return self._wireAudio(ctx);
          });
        }
        return self._wireAudio(ctx);
      })
      .then(function () {
        if (self._onWake) {
          try {
            self._onWake();
          } catch (e) {
            console.error("[NovaWakeClient] onWake error:", e);
          }
        }
      });
  };

  /**
   * @param {AudioContext} ctx
   * @returns {void}
   */
  NovaWakeClient.prototype._wireAudio = function _wireAudio(ctx) {
    var self = this;
    var inputRate = ctx.sampleRate;
    this._source = ctx.createMediaStreamSource(this._mediaStream);
    this._mute = ctx.createGain();
    this._mute.gain.value = 0;
    this._processor = ctx.createScriptProcessor(this._bufferSize, 1, 1);
    this._processor.onaudioprocess = function (evt) {
      if (!self._running || typeof window.NovaWakeEngine === "undefined") {
        return;
      }
      var input = evt.inputBuffer.getChannelData(0);
      var pcm16;
      if (
        typeof window.NovaStreamClient !== "undefined" &&
        typeof window.NovaStreamClient._downsampleToInt16 === "function"
      ) {
        pcm16 = window.NovaStreamClient._downsampleToInt16(
          input,
          inputRate,
          self._targetSampleRate
        );
      } else {
        pcm16 = downsampleToInt16(input, inputRate, self._targetSampleRate);
      }
      var floatFrame = int16ToFloat32(pcm16);
      if (floatFrame.length > 0) {
        window.NovaWakeEngine.process(floatFrame);
      }
    };
    this._source.connect(this._processor);
    this._processor.connect(this._mute);
    this._mute.connect(ctx.destination);
    this._running = true;
  };

  /**
   * Stop mic and tear down the audio graph.
   *
   * @returns {void}
   */
  NovaWakeClient.prototype.stop = function stop() {
    this._running = false;
    if (this._processor) {
      try {
        this._processor.disconnect();
      } catch (e) {
        /* ignore */
      }
      this._processor.onaudioprocess = null;
      this._processor = null;
    }
    if (this._source) {
      try {
        this._source.disconnect();
      } catch (e) {
        /* ignore */
      }
      this._source = null;
    }
    if (this._mute) {
      try {
        this._mute.disconnect();
      } catch (e) {
        /* ignore */
      }
      this._mute = null;
    }
    if (this._audioContext) {
      this._audioContext.close().catch(function () {});
      this._audioContext = null;
    }
    if (this._mediaStream) {
      this._mediaStream.getTracks().forEach(function (t) {
        t.stop();
      });
      this._mediaStream = null;
    }
  };

  window.NovaWakeClient = NovaWakeClient;
})();
