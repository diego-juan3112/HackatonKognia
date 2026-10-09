// AudioWorklet processor for MicTap (src/voice/audio/mic-tap.ts).
// Plain JavaScript on purpose: it is served as a static file so that
// `audioWorklet.addModule()` works in the static Astro build.
//
// It forwards the first input channel in ~20 ms blocks of Float32 samples at
// the context sample rate. Resampling and PCM16 conversion happen on the main
// thread, where the target rate of the active engine is known.
class MicCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.blockSize = Math.round(sampleRate / 50);
    this.block = new Float32Array(this.blockSize);
    this.filled = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    let offset = 0;
    while (offset < channel.length) {
      const n = Math.min(channel.length - offset, this.blockSize - this.filled);
      this.block.set(channel.subarray(offset, offset + n), this.filled);
      this.filled += n;
      offset += n;
      if (this.filled === this.blockSize) {
        const out = this.block;
        this.port.postMessage(out, [out.buffer]);
        this.block = new Float32Array(this.blockSize);
        this.filled = 0;
      }
    }
    return true;
  }
}

registerProcessor("mic-capture", MicCaptureProcessor);
