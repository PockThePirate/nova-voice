/**
 * AudioWorkletProcessor: forwards mono input as Float32 chunks to the main thread.
 * Register name must match AudioWorkletNode constructor: "nova-capture".
 *
 * Loaded with: audioContext.audioWorklet.addModule("/static/js/nova_capture_worklet.js")
 *
 * Example:
 *   new AudioWorkletNode(ctx, "nova-capture", { channelCount: 1, numberOfInputs: 1, numberOfOutputs: 1 })
 */
class NovaCaptureProcessor extends AudioWorkletProcessor {
  /**
   * @param {Float32Array[][]} inputs
   * @param {Float32Array[][]} outputs
   * @returns {boolean} true to keep processor alive
   */
  process(inputs, outputs) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const ch0 = input[0];
      if (ch0 && ch0.length > 0) {
        const copy = new Float32Array(ch0.length);
        copy.set(ch0);
        this.port.postMessage(copy);
      }
    }
    const out0 = outputs[0];
    if (out0 && out0.length > 0 && out0[0]) {
      out0[0].fill(0);
    }
    return true;
  }
}

registerProcessor("nova-capture", NovaCaptureProcessor);
