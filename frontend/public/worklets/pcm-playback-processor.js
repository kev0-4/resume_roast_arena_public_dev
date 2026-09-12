/**
 * Plays the 24kHz 16-bit PCM the Live API streams back.
 *
 * Chunks arrive faster and in different sizes than the audio thread
 * consumes them, so they're queued here and drained sample-by-sample.
 * The page creates this worklet's AudioContext with { sampleRate: 24000 }
 * to match the API's output rate exactly -- no resampling, no pitch shift.
 *
 * Barge-in is why the queue lives here rather than in a series of
 * scheduled buffer nodes: when the user interrupts, the model's remaining
 * audio has to stop *instantly*. A "clear" message drops everything
 * pending in one go, which is impossible once buffers are scheduled ahead
 * on the audio clock.
 */
class PcmPlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    /** @type {Int16Array[]} */
    this.queue = [];
    this.offset = 0;
    this.wasPlaying = false;

    this.port.onmessage = (event) => {
      const data = event.data;
      if (data === "clear") {
        // Interruption: drop everything still pending.
        this.queue = [];
        this.offset = 0;
        return;
      }
      this.queue.push(new Int16Array(data));
    };
  }

  process(_inputs, outputs) {
    const out = outputs[0][0];
    if (!out) return true;

    let written = 0;
    while (written < out.length && this.queue.length > 0) {
      const current = this.queue[0];
      const remaining = current.length - this.offset;
      const toWrite = Math.min(remaining, out.length - written);

      for (let i = 0; i < toWrite; i++) {
        out[written + i] = current[this.offset + i] / 0x8000;
      }

      written += toWrite;
      this.offset += toWrite;

      if (this.offset >= current.length) {
        this.queue.shift();
        this.offset = 0;
      }
    }

    // Underrun (or nothing queued) -- emit silence for the rest.
    for (let i = written; i < out.length; i++) out[i] = 0;

    // Let the page drive "is the interviewer speaking right now" off the
    // real state of the audio queue rather than guessing from message
    // timing, which lags and makes the visualiser feel disconnected.
    const isPlaying = this.queue.length > 0 || written > 0;
    if (isPlaying !== this.wasPlaying) {
      this.wasPlaying = isPlaying;
      this.port.postMessage({ playing: isPlaying });
    }

    return true;
  }
}

registerProcessor("pcm-playback-processor", PcmPlaybackProcessor);
