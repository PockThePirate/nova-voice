/**
 * Nova voice streaming over WebSocket: JSON `start` / `stop` control messages and
 * binary Int16 mono PCM at 16 kHz after the socket is open.
 *
 * @example
 * const client = new NovaStreamClient({ path: "/ws/audio/nova" });
 * client.onReady = () => client.startCapture();
 * client.connect();
 */
class NovaStreamClient {
  /**
   * @param {Object} [options]
   * @param {string} [options.path="/ws/audio/nova"] WebSocket path on current host (ignored if wsUrl set)
   * @param {string} [options.wsUrl] Full WebSocket URL (ws: or wss:), e.g. for dev behind a different port
   * @param {number} [options.targetSampleRate=16000] Declared to server and used for PCM
   * @param {number} [options.bufferSize=4096] ScriptProcessor fallback buffer size (power of two)
   * @param {string} [options.workletModuleUrl="/static/js/nova_capture_worklet.js"] URL for AudioWorklet module
   */
  constructor(options) {
    const o = options || {};
    this.path = typeof o.path === "string" ? o.path : "/ws/audio/nova";
    this.wsUrl =
      typeof o.wsUrl === "string" && (o.wsUrl.indexOf("ws:") === 0 || o.wsUrl.indexOf("wss:") === 0)
        ? o.wsUrl
        : null;
    this.targetSampleRate = typeof o.targetSampleRate === "number" ? o.targetSampleRate : 16000;
    this.bufferSize = typeof o.bufferSize === "number" ? o.bufferSize : 4096;
    this.workletModuleUrl =
      typeof o.workletModuleUrl === "string" ? o.workletModuleUrl : "/static/js/nova_capture_worklet.js";

    this.ws = null;
    /** @type {string|null} Same id sent in the `start` message */
    this.sessionId = null;
    this.mediaStream = null;
    this.audioContext = null;
    this.scriptProcessor = null;
    /** @type {AudioWorkletNode|null} */
    this.workletNode = null;
    this.sourceNode = null;
    /** @type {string[]} Pending JSON control messages before the socket is open */
    this.queue = [];
    this._captureActive = false;
    /** When true, `onConnectionLost` is not fired (user called `disconnect()`). */
    this._closingByUser = false;
    /** @type {ReturnType<typeof setTimeout>|null} */
    this._voicePipelineTimer = null;
    /** After `stop`, wait for `reply` / `error` before closing the socket. */
    this._awaitVoicePipeline = false;

    /** Called after WebSocket is open and `start` has been sent */
    this.onReady = null;
    /** @param {MessageEvent} event */
    this.onMessage = null;
    /** @param {Event} event */
    this.onConnectionLost = null;
    /** Fires when user-initiated disconnect finishes (socket closed, including after voice pipeline). */
    this.onUserDisconnected = null;
  }

  /**
   * Whether the socket is open.
   * @returns {boolean}
   */
  isOpen() {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  /**
   * Open WebSocket and send `start` with a new session id (stored on `this.sessionId`).
   */
  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    this.sessionId = NovaStreamClient._newSessionId();

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url = this.wsUrl || `${proto}://${window.location.host}${this.path}`;
    window.__NOVA_WS_TARGET_URL__ = url;
    if (typeof console !== "undefined" && console.info) {
      console.info("[Nova] WebSocket connecting:", url, "(DevTools: Network, enable Preserve log, filter WS, then Wake Nova)");
    }
    this.ws = new WebSocket(url);
    this.ws.binaryType = "arraybuffer";

    this.ws.onopen = () => {
      window.NOVA_STREAM_FAILED = false;
      this._flushControlQueue();
      this._sendJson({
        type: "start",
        session_id: this.sessionId,
        sample_rate: this.targetSampleRate,
      });
      if (typeof this.onReady === "function") {
        try {
          this.onReady();
        } catch (e) {
          console.error("NovaStreamClient onReady error:", e);
        }
      }
    };

    this.ws.onmessage = (event) => {
      if (this._awaitVoicePipeline) {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "reply" || data.type === "error") {
            this._awaitVoicePipeline = false;
            if (this._voicePipelineTimer) {
              clearTimeout(this._voicePipelineTimer);
              this._voicePipelineTimer = null;
            }
            if (typeof this.onMessage === "function") {
              try {
                this.onMessage(event);
              } catch (e) {
                console.error("NovaStreamClient onMessage error:", e);
              }
            }
            this._completeUserDisconnect();
            return;
          }
        } catch (e) {
          /* fall through */
        }
      }
      if (typeof this.onMessage === "function") {
        try {
          this.onMessage(event);
        } catch (e) {
          console.error("NovaStreamClient onMessage error:", e);
        }
      }
    };

    this.ws.onerror = () => {
      window.NOVA_STREAM_FAILED = true;
    };

    this.ws.onclose = (event) => {
      if (this._voicePipelineTimer) {
        clearTimeout(this._voicePipelineTimer);
        this._voicePipelineTimer = null;
      }
      this._awaitVoicePipeline = false;
      this.ws = null;
      this.stopCapture();
      const userInitiated = this._closingByUser;
      this._closingByUser = false;
      if (userInitiated && typeof this.onUserDisconnected === "function") {
        try {
          this.onUserDisconnected(event);
        } catch (e) {
          console.error("NovaStreamClient onUserDisconnected error:", e);
        }
      }
      if (!userInitiated && typeof this.onConnectionLost === "function") {
        try {
          this.onConnectionLost(event);
        } catch (e) {
          console.error("NovaStreamClient onConnectionLost error:", e);
        }
      }
    };
  }

  /**
   * Stop microphone processing, send `stop`, and close the socket (optionally after voice reply).
   * @param {Object} [options]
   * @param {boolean} [options.waitForVoicePipeline] If true, keep WS open until `reply`/`error` or timeout
   * @param {number} [options.voicePipelineTimeoutMs] Max wait ms (default 120000)
   */
  disconnect(options) {
    const opts = options || {};
    const wait = opts.waitForVoicePipeline === true;
    this._closingByUser = true;
    this.stopCapture();
    const canSendStop = this.ws && this.ws.readyState === WebSocket.OPEN && this.sessionId;
    if (canSendStop) {
      this._sendJson({
        type: "stop",
        session_id: this.sessionId,
      });
    }
    if (wait && canSendStop) {
      this._awaitVoicePipeline = true;
      const ms =
        typeof opts.voicePipelineTimeoutMs === "number" && opts.voicePipelineTimeoutMs > 0
          ? opts.voicePipelineTimeoutMs
          : 120000;
      const self = this;
      this._voicePipelineTimer = setTimeout(function () {
        self._awaitVoicePipeline = false;
        self._completeUserDisconnect();
      }, ms);
      return;
    }
    this._completeUserDisconnect();
  }

  /**
   * Close WebSocket and clear session (used after voice pipeline or immediate disconnect).
   */
  _completeUserDisconnect() {
    if (this._voicePipelineTimer) {
      clearTimeout(this._voicePipelineTimer);
      this._voicePipelineTimer = null;
    }
    this._awaitVoicePipeline = false;
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    } else {
      this._closingByUser = false;
    }
    this.sessionId = null;
    this.queue.length = 0;
  }

  /**
   * Request microphone access and stream 16 kHz mono PCM frames as binary messages.
   * @returns {Promise<void>}
   */
  async startCapture() {
    if (this._captureActive) {
      return;
    }
    if (!this.isOpen()) {
      throw new Error("NovaStreamClient: WebSocket must be open before startCapture()");
    }

    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        channelCount: 1,
      },
      video: false,
    });

    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    this.audioContext = new AudioCtx();
    const inputRate = this.audioContext.sampleRate;
    if (this.audioContext.state === "suspended") {
      await this.audioContext.resume();
    }

    this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);
    const mute = this.audioContext.createGain();
    mute.gain.value = 0;

    const canWorklet =
      this.audioContext.audioWorklet && typeof this.audioContext.audioWorklet.addModule === "function";

    if (canWorklet) {
      try {
        await this.audioContext.audioWorklet.addModule(this.workletModuleUrl);
        this.workletNode = new AudioWorkletNode(this.audioContext, "nova-capture", {
          numberOfInputs: 1,
          numberOfOutputs: 1,
          channelCount: 1,
          channelCountMode: "explicit",
        });
        const client = this;
        this.workletNode.port.onmessage = function (ev) {
          if (!client.isOpen() || !client.sessionId) {
            return;
          }
          const input = ev.data;
          if (!(input instanceof Float32Array)) {
            return;
          }
          const pcm = NovaStreamClient._downsampleToInt16(input, inputRate, client.targetSampleRate);
          if (pcm && pcm.byteLength > 0) {
            client._sendBinary(pcm.buffer);
          }
        };
        this.sourceNode.connect(this.workletNode);
        this.workletNode.connect(mute);
        mute.connect(this.audioContext.destination);
        this._captureActive = true;
        return;
      } catch (err) {
        console.warn("NovaStreamClient: AudioWorklet failed, using ScriptProcessor fallback:", err);
        if (this.workletNode) {
          try {
            this.workletNode.port.onmessage = null;
            this.workletNode.disconnect();
          } catch (e2) {
            /* ignore */
          }
          this.workletNode = null;
        }
      }
    }

    this.scriptProcessor = this.audioContext.createScriptProcessor(this.bufferSize, 1, 1);
    const self = this;
    this.scriptProcessor.onaudioprocess = function (evt) {
      if (!self.isOpen() || !self.sessionId) {
        return;
      }
      const input = evt.inputBuffer.getChannelData(0);
      const pcm = NovaStreamClient._downsampleToInt16(input, inputRate, self.targetSampleRate);
      if (pcm && pcm.byteLength > 0) {
        self._sendBinary(pcm.buffer);
      }
    };
    this.sourceNode.connect(this.scriptProcessor);
    this.scriptProcessor.connect(mute);
    mute.connect(this.audioContext.destination);
    this._captureActive = true;
  }

  /**
   * Stop microphone and audio graph; does not close the WebSocket.
   */
  stopCapture() {
    this._captureActive = false;
    if (this.workletNode) {
      try {
        this.workletNode.port.onmessage = null;
        this.workletNode.disconnect();
      } catch (e) {
        /* ignore */
      }
      this.workletNode = null;
    }
    if (this.scriptProcessor) {
      try {
        this.scriptProcessor.disconnect();
      } catch (e) {
        /* ignore */
      }
      this.scriptProcessor.onaudioprocess = null;
      this.scriptProcessor = null;
    }
    if (this.sourceNode) {
      try {
        this.sourceNode.disconnect();
      } catch (e) {
        /* ignore */
      }
      this.sourceNode = null;
    }
    if (this.audioContext) {
      this.audioContext.close().catch(function () {});
      this.audioContext = null;
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(function (t) {
        t.stop();
      });
      this.mediaStream = null;
    }
  }

  /**
   * @param {Object} payload
   */
  _sendJson(payload) {
    const raw = JSON.stringify(payload);
    if (this.isOpen()) {
      this.ws.send(raw);
    } else {
      this.queue.push(raw);
    }
  }

  /**
   * @param {ArrayBuffer} buf
   */
  _sendBinary(buf) {
    if (this.isOpen()) {
      this.ws.send(buf);
    }
  }

  _flushControlQueue() {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }
    while (this.queue.length > 0) {
      const item = this.queue.shift();
      if (typeof item === "string") {
        this.ws.send(item);
      }
    }
  }

  /**
   * @returns {string}
   */
  static _newSessionId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      const v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  /**
   * @param {Float32Array} input
   * @param {number} inputRate
   * @param {number} outputRate
   * @returns {Int16Array}
   */
  static _downsampleToInt16(input, inputRate, outputRate) {
    if (outputRate >= inputRate) {
      return NovaStreamClient._floatToInt16(input);
    }
    const ratio = inputRate / outputRate;
    const outLength = Math.max(1, Math.floor(input.length / ratio));
    const out = new Int16Array(outLength);
    let pos = 0;
    for (let i = 0; i < outLength; i++) {
      const srcIndex = Math.min(input.length - 1, Math.floor(pos));
      let s = input[srcIndex];
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
  static _floatToInt16(input) {
    const out = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      let s = input[i];
      if (s > 1) {
        s = 1;
      } else if (s < -1) {
        s = -1;
      }
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }
}

window.NovaStreamClient = NovaStreamClient;
