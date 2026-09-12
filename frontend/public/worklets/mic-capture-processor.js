/**
 * Captures microphone audio and hands it to the main thread as 16-bit PCM.
 *
 * The Live API wants raw PCM, little-endian, 16-bit, mono at 16kHz. Rather
 * than resample here (the classic source of "it sounds like a chipmunk"
 * bugs), the page creates this worklet's AudioContext with
 * { sampleRate: 16000 }, so the browser resamples the mic for us and every
 * buffer that arrives is already at the right rate. All this has to do is
 * Float32 [-1,1] -> Int16.
 *
 * Plain JS in public/ rather than TypeScript in src/: AudioWorklet modules
 * are fetched by URL at runtime (audioWorklet.addModule('/worklets/...')),
 * so they are never part of the bundle and can't be .ts.
 */
class MicCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    // No input yet (mic still warming up) -- keep the node alive.
    if (!channel || channel.length === 0) return true;

    const pcm = new Int16Array(channel.length);
    for (let i = 0; i < channel.length; i++) {
      // Clamp before scaling: values can overshoot [-1,1] slightly and
      // wrap around to the opposite sign if left unchecked, which sounds
      // like a loud click.
      const sample = Math.max(-1, Math.min(1, channel[i]));
      pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }

    // Transfer the buffer rather than copying it -- this runs every
    // ~128 frames and copying adds avoidable GC churn on the audio thread.
    this.port.postMessage(pcm.buffer, [pcm.buffer]);
    return true;
  }
}

registerProcessor("mic-capture-processor", MicCaptureProcessor);
