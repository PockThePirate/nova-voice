/**
 * Mic-level end-of-utterance for wake command capture (parallel to Web Speech).
 * Calibrates noise floor over a short window then mirrors NovaStreamClient silence logic.
 */
(function () {
  "use strict";

  var LEVEL_CALIBRATION_MS = 320;
  var LEVEL_SILENCE_MS = 2000;
  var LEVEL_MIN_SILENCE_THRESHOLD = 0.008;
  var LEVEL_MAX_SILENCE_THRESHOLD = 0.1;
  var LEVEL_MIN_SPEECH_THRESHOLD = 0.018;
  var LEVEL_MAX_SPEECH_THRESHOLD = 0.14;
  var SILENCE_MULT = 1.55;
  var SPEECH_MULT = 3.0;
  var BUFFER_SIZE = 2048;

  /**
   * Per-frame peak-based silence detection with post-wake calibration.
   *
   * General purpose: run alongside SpeechRecognition; call `beginCalibration()` when
   * the wake phrase fires so `noiseFloor` reflects room/TV level at that instant.
   *
   * @param {Object} [options]
   * @param {number} [options.calibrationMs=320] Duration to collect frame peaks for floor
   * @param {number} [options.silenceTimeoutMs=2000] Ms below silence threshold after speech
   * @param {function(): void} [options.onLevelSilence] Fired once when silence budget exceeded
   *
   * @example
   * var m = new WakeCommandLevelMonitor({
   *   onLevelSilence: function () { finalizeCapture(); },
   * });
   * m.start().then(function () { m.beginCalibration(); });
   */
  function WakeCommandLevelMonitor(options) {
    var o = options || {};
    this.calibrationMs =
      typeof o.calibrationMs === "number" ? o.calibrationMs : LEVEL_CALIBRATION_MS;
    this.silenceTimeoutMs =
      typeof o.silenceTimeoutMs === "number" ? o.silenceTimeoutMs : LEVEL_SILENCE_MS;
    this.onLevelSilence = typeof o.onLevelSilence === "function" ? o.onLevelSilence : null;

    this._mediaStream = null;
    this._audioContext = null;
    this._processor = null;
    this._source = null;
    this._mute = null;

    this._calibrating = false;
    /** @type {number[]} */
    this._calibrationSamples = [];
    this._calibrationAccumMs = 0;

    this._calibrationDone = false;
    this._silenceThreshold = 0.02;
    this._speechThreshold = 0.04;

    this._hasSpoken = false;
    this._silenceMs = 0;
  }

  /**
   * Request mic and attach ScriptProcessor for level frames.
   *
   * @returns {Promise<void>}
   */
  WakeCommandLevelMonitor.prototype.start = function start() {
    var self = this;
    if (this._mediaStream) {
      return Promise.resolve();
    }
    return navigator.mediaDevices
      .getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
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
            return self._wireGraph();
          });
        }
        return self._wireGraph();
      });
  };

  /**
   * Connect nodes after AudioContext is running.
   *
   * @returns {void}
   */
  WakeCommandLevelMonitor.prototype._wireGraph = function _wireGraph() {
    var ctx = this._audioContext;
    var inputRate = ctx.sampleRate;
    this._source = ctx.createMediaStreamSource(this._mediaStream);
    this._mute = ctx.createGain();
    this._mute.gain.value = 0;
    this._processor = ctx.createScriptProcessor(BUFFER_SIZE, 1, 1);
    var self = this;
    this._processor.onaudioprocess = function (evt) {
      var input = evt.inputBuffer.getChannelData(0);
      self._handleFrame(input, inputRate);
    };
    this._source.connect(this._processor);
    this._processor.connect(this._mute);
    this._mute.connect(ctx.destination);
  };

  /**
   * Reset calibration baseline; call immediately when wake is detected.
   *
   * @returns {void}
   */
  WakeCommandLevelMonitor.prototype.beginCalibration = function beginCalibration() {
    this._calibrating = true;
    this._calibrationSamples = [];
    this._calibrationAccumMs = 0;
    this._calibrationDone = false;
    this._hasSpoken = false;
    this._silenceMs = 0;
  };

  /**
   * Apply 80th percentile of calibration peaks as noise floor; set thresholds.
   *
   * @returns {void}
   */
  WakeCommandLevelMonitor.prototype._finishCalibration = function _finishCalibration() {
    this._calibrating = false;
    this._calibrationDone = true;
    var arr = this._calibrationSamples.slice().sort(function (a, b) {
      return a - b;
    });
    if (arr.length === 0) {
      this._silenceThreshold = 0.02;
      this._speechThreshold = 0.04;
      return;
    }
    var idx = Math.floor(arr.length * 0.8);
    var noiseFloor = arr[Math.min(idx, arr.length - 1)];
    this._silenceThreshold = Math.max(
      LEVEL_MIN_SILENCE_THRESHOLD,
      Math.min(LEVEL_MAX_SILENCE_THRESHOLD, noiseFloor * SILENCE_MULT)
    );
    this._speechThreshold = Math.max(
      LEVEL_MIN_SPEECH_THRESHOLD,
      Math.min(LEVEL_MAX_SPEECH_THRESHOLD, noiseFloor * SPEECH_MULT)
    );
    if (this._speechThreshold <= this._silenceThreshold) {
      this._speechThreshold = this._silenceThreshold + 0.012;
    }
  };

  /**
   * One audio buffer: update calibration or silence accumulation.
   *
   * @param {Float32Array} frame
   * @param {number} inputRate
   * @returns {void}
   */
  WakeCommandLevelMonitor.prototype._handleFrame = function _handleFrame(frame, inputRate) {
    if (!frame || frame.length === 0) {
      return;
    }
    var maxAbs = 0;
    var i;
    for (i = 0; i < frame.length; i++) {
      var v = frame[i];
      var a = v < 0 ? -v : v;
      if (a > maxAbs) {
        maxAbs = a;
      }
    }
    var frameMs = (frame.length / inputRate) * 1000;

    if (this._calibrating) {
      this._calibrationSamples.push(maxAbs);
      this._calibrationAccumMs += frameMs;
      if (this._calibrationAccumMs >= this.calibrationMs) {
        this._finishCalibration();
      }
      return;
    }

    if (!this._calibrationDone) {
      return;
    }

    if (this.silenceTimeoutMs <= 0) {
      return;
    }

    if (maxAbs >= this._speechThreshold) {
      this._hasSpoken = true;
      this._silenceMs = 0;
      return;
    }

    if (!this._hasSpoken) {
      return;
    }

    if (maxAbs < this._silenceThreshold) {
      this._silenceMs += frameMs;
      if (this._silenceMs >= this.silenceTimeoutMs) {
        this._silenceMs = 0;
        this._hasSpoken = false;
        if (this.onLevelSilence) {
          try {
            this.onLevelSilence();
          } catch (e) {
            console.error("[Wake] onLevelSilence error:", e);
          }
        }
      }
    } else {
      this._silenceMs = 0;
    }
  };

  /**
   * Stop tracks and tear down nodes.
   *
   * @returns {void}
   */
  WakeCommandLevelMonitor.prototype.stop = function stop() {
    this._calibrating = false;
    this._calibrationDone = false;
    this.onLevelSilence = null;

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

  window.WakeCommandLevelMonitor = WakeCommandLevelMonitor;
})();
