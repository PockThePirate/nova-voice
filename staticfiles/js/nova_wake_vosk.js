(function () {
  "use strict";

  /**
   * NovaWakeEngine (Vosk-Browser integration)
   *
   * Uses vosk-browser (npm package) for wake word detection.
   * Requires vosk.js to be loaded before this script.
   */

  if (!window.NovaWakeEngine) {
    window.NovaWakeEngine = {};
  }

  var _config = {
    wakePhrases: ["nova", "hey nova"],
    modelPath: "/static/vosk/model-en/vosk-model-small-en-us-0.15.tar.gz",
    sampleRate: 16000,
    debug: true,
  };
  var _model = null;
  var _recognizer = null;
  var _ready = false;
  var _pendingInit = null;
  var _onWake = null;
  var _audioContext = null;

  function logDebug() {
    if (!_config.debug) return;
    if (typeof console !== "undefined" && console.info) {
      console.info.apply(console, ["[NovaWakeEngine]"].concat(Array.prototype.slice.call(arguments)));
    }
  }

  window.NovaWakeEngine.setOnWake = function setOnWake(cb) {
    _onWake = typeof cb === "function" ? cb : null;
  };

  function maybeFireWake() {
    if (typeof _onWake === "function") {
      try {
        _onWake();
      } catch (e) {
        console.error("NovaWakeEngine onWake callback error", e);
      }
    }
  }

  function checkWakePhrase(text) {
    if (!text) return;
    var lower = String(text).toLowerCase().trim();
    for (var i = 0; i < _config.wakePhrases.length; i++) {
      var phrase = _config.wakePhrases[i];
      if (phrase && lower.indexOf(phrase) !== -1) {
        logDebug("Wake phrase detected:", phrase, "in", lower);
        maybeFireWake();
        return true;
      }
    }
    return false;
  }

  window.NovaWakeEngine.init = async function initNovaWakeEngine(config) {
    if (_pendingInit) {
      return _pendingInit;
    }
    _pendingInit = (async function () {
      _config = Object.assign({}, _config, config || {});
      logDebug("Initializing with config:", _config);

      if (typeof window.Vosk === "undefined") {
        throw new Error("Vosk not loaded. Make sure to include vosk.js before nova_wake_vosk.js");
      }

      // Create model (loads in Web Worker)
      logDebug("Loading Vosk model from:", _config.modelPath);
      _model = await Vosk.createModel(_config.modelPath);
      
      _model.on("error", function(e) {
        console.error("Vosk model error:", e);
      });

      // Create recognizer (vosk-browser requires sample rate as first constructor arg)
      _recognizer = new _model.KaldiRecognizer(Number(_config.sampleRate) || 16000);
      
      _recognizer.on("result", function(message) {
        var text = message.result.text;
        logDebug("Final result:", text);
        checkWakePhrase(text);
      });

      _recognizer.on("partialresult", function(message) {
        var partial = message.result.partial;
        if (partial) {
          logDebug("Partial result:", partial);
          checkWakePhrase(partial);
        }
      });

      _ready = true;
      logDebug("Vosk wake engine ready");
      return true;
    })();
    return _pendingInit;
  };

  /**
   * Convert Float32Array to Int16Array for Vosk
   */
  function floatToInt16(frame) {
    if (!frame || frame.length === 0) return null;
    var out = new Int16Array(frame.length);
    for (var i = 0; i < frame.length; i++) {
      var s = frame[i];
      if (s > 1) s = 1;
      else if (s < -1) s = -1;
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }

  /**
   * Create an AudioBuffer from Int16 PCM data for Vosk
   */
  function createAudioBuffer(int16Data, sampleRate) {
    var buffer = new AudioBuffer({
      length: int16Data.length,
      sampleRate: sampleRate || _config.sampleRate,
      numberOfChannels: 1
    });
    var channelData = buffer.getChannelData(0);
    // Convert Int16 back to Float32 for AudioBuffer
    for (var i = 0; i < int16Data.length; i++) {
      channelData[i] = int16Data[i] / 32768.0;
    }
    return buffer;
  }

  window.NovaWakeEngine.process = function processNovaWakeFrame(pcmFrame) {
    if (!_ready || !_recognizer || !pcmFrame || pcmFrame.length === 0) {
      return;
    }

    try {
      // Convert Float32 to Int16
      var pcm16 = floatToInt16(pcmFrame);
      if (!pcm16) return;

      // Create AudioBuffer for Vosk
      var audioBuffer = createAudioBuffer(pcm16, _config.sampleRate);
      
      // Feed to recognizer
      _recognizer.acceptWaveform(audioBuffer);
    } catch (e) {
      console.error("NovaWakeEngine.process error:", e);
    }
  };

  window.NovaWakeEngine.reset = function resetNovaWakeEngine() {
    if (_recognizer) {
      // Vosk-browser doesn't have a direct reset, but we can remove and recreate
      _recognizer.remove();
      _recognizer = new _model.KaldiRecognizer(Number(_config.sampleRate) || 16000);
      _recognizer.on("result", function(message) {
        checkWakePhrase(message.result.text);
      });
      _recognizer.on("partialresult", function(message) {
        checkWakePhrase(message.result.partial);
      });
    }
  };

  window.NovaWakeEngine.terminate = function terminateNovaWakeEngine() {
    if (_model) {
      _model.terminate();
      _model = null;
      _recognizer = null;
      _ready = false;
      _pendingInit = null;
    }
  };
})();
