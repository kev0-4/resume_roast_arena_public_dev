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
    // Reported back so the page can tell "the model is slow" apart from
    // "the model answered ages ago and we're still playing a backlog".
    this.queuedSamples = 0;
    this.sinceReport = 0;

    this.port.onmessage = (event) => {
      const data = event.data;
      if (data === "clear") {
        // Interruption: drop everything still pending.
        this.queue = [];
        this.offset = 0;
        this.queuedSamples = 0;
        return;
      }
      const chunk = new Int16Array(data);
      this.queue.push(chunk);
      this.queuedSamples += chunk.length;
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
      this.queuedSamples -= toWrite;

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
      this.port.postMessage({ playing: isPlaying, queuedSamples: this.queuedSamples });
    }

    // Periodic depth report (~every 250ms) so a growing backlog is visible
    // even while playback state itself never changes.
    this.sinceReport += out.length;
    if (this.sinceReport >= sampleRate / 4) {
      this.sinceReport = 0;
      this.port.postMessage({ queuedSamples: this.queuedSamples });
    }

    return true;
  }
}

registerProcessor("pcm-playback-processor", PcmPlaybackProcessor);
