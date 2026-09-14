// Browser audio plumbing for the real-time interview.
//
// Two separate AudioContexts, each pinned to the rate the Gemini Live API
// actually uses: 16kHz for the mic going out, 24kHz for the model's voice
// coming back. Letting the browser resample at the context boundary means
// there is no hand-written resampling anywhere in this codebase -- that
// was the single likeliest source of "the audio sounds wrong" bugs.
//
// Worklet source lives in public/worklets/*.js because AudioWorklet modules
// are loaded by URL at runtime and never go through the bundler.

const MIC_SAMPLE_RATE = 16000;
const PLAYBACK_SAMPLE_RATE = 24000;

export const MIC_MIME_TYPE = `audio/pcm;rate=${MIC_SAMPLE_RATE}`;

/**
 * How much louder than the measured echo floor real speech has to be
 * before it gets through while the interviewer is talking.
 *
 * The browser's own echoCancellation does not reliably cover audio played
 * through a separate AudioContext, so without this the interviewer hears
 * itself. Since the API defaults to START_OF_ACTIVITY_INTERRUPTS, that
 * reads as the candidate barging in and the model cuts its own generation
 * off -- reproduced by looping model audio back into the mic: replies
 * dropped to 2/4 and the opening line was truncated, against 4/4 on a
 * clean mic.
 */
const BARGE_IN_RATIO = 4;

/** Absolute floor, so a silent room can't make the gate hair-trigger. */
const BARGE_IN_MIN_RMS = 0.02;

/**
 * Should this mic chunk be forwarded while the interviewer is speaking?
 *
 * Pure so it can be reasoned about and tested without a microphone.
 * `echoFloor` is the running estimate of how loud the room is purely from
 * the interviewer's own voice leaking back in.
 */
export function shouldForwardWhileSpeaking(rms: number, echoFloor: number): boolean {
  return rms > Math.max(BARGE_IN_MIN_RMS, echoFloor * BARGE_IN_RATIO);
}

function rmsOf(samples: Int16Array): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) {
    const v = samples[i] / 0x8000;
    sum += v * v;
  }
  return Math.sqrt(sum / samples.length);
}

/** Int16 PCM -> base64, which is the encoding sendRealtimeInput expects. */
function toBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  // Chunked rather than String.fromCharCode(...bytes): a whole audio buffer
  // spread into arguments blows the call stack on longer chunks.
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

/** base64 -> ArrayBuffer, for the model's audio arriving as inlineData. */
function fromBase64(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

export class MicCapture {
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  private muted = false;
  private chunksSent = 0;
  private actualSampleRate = 0;
  /** True while the interviewer is audibly speaking. */
  private interviewerSpeaking = false;
  /** Running estimate of mic level caused purely by the interviewer's own
   *  voice leaking back in through the speakers. */
  private echoFloor = 0;
  private suppressed = 0;

  /** Fires for every captured chunk, already base64-encoded 16kHz PCM. */
  constructor(private readonly onChunk: (base64: string) => void) {}

  /** Chunks handed to the socket so far -- proves the mic is still alive.
   *  `suppressed` counts chunks withheld as echo, which is the number that
   *  tells you someone isn't wearing headphones. */
  stats(): { chunksSent: number; sampleRate: number; suppressed: number; echoFloor: number } {
    return {
      chunksSent: this.chunksSent,
      sampleRate: this.actualSampleRate,
      suppressed: this.suppressed,
      echoFloor: Number(this.echoFloor.toFixed(4)),
    };
  }

  /** Told by the page whenever playback starts or stops. */
  setInterviewerSpeaking(speaking: boolean): void {
    this.interviewerSpeaking = speaking;
  }

  async start(): Promise<void> {
    // Echo cancellation matters more than usual here: without it the mic
    // picks up the interviewer's own voice from the speakers and the model
    // interrupts itself. Headphones are still the reliable fix.
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    this.context = new AudioContext({ sampleRate: MIC_SAMPLE_RATE });
    // If the browser refused 16kHz, every chunk we send is mislabelled as
    // rate=16000 and the model hears a distorted stream.
    this.actualSampleRate = this.context.sampleRate;
    await this.context.audioWorklet.addModule("/worklets/mic-capture-processor.js");

    const source = this.context.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.context, "mic-capture-processor");
    this.node.port.onmessage = (event) => {
      if (this.muted) return;
      const buffer = event.data as ArrayBuffer;

      if (this.interviewerSpeaking) {
        const rms = rmsOf(new Int16Array(buffer));
        // Learn the echo level from the quiet moments while the
        // interviewer talks, tracking upward slowly so one cough doesn't
        // raise the bar permanently.
        this.echoFloor = this.echoFloor === 0 ? rms : this.echoFloor * 0.95 + rms * 0.05;
        if (!shouldForwardWhileSpeaking(rms, this.echoFloor)) {
          this.suppressed++;
          return;
        }
      }

      this.chunksSent++;
      this.onChunk(toBase64(buffer));
    };

    // Not connected to destination -- routing the mic to the speakers would
    // be an instant feedback loop.
    source.connect(this.node);
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    // Also disable the track itself, so the browser's own mic indicator
    // reflects reality rather than us silently dropping chunks.
    this.stream?.getAudioTracks().forEach((t) => (t.enabled = !muted));
  }

  async stop(): Promise<void> {
    this.node?.port.close();
    this.node?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    await this.context?.close().catch(() => {});
    this.node = null;
    this.stream = null;
    this.context = null;
  }
}

export class PcmPlayer {
  private context: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;
  private analyser: AnalyserNode | null = null;
  private amplitudeData: Uint8Array | null = null;
  /** Unplayed audio still queued, in seconds. */
  private queuedSeconds = 0;
  /** What the browser ACTUALLY gave us, which need not be what we asked. */
  private actualSampleRate = 0;

  /** Fires when the interviewer starts/stops actually producing sound. */
  constructor(private readonly onSpeakingChange: (speaking: boolean) => void) {}

  async start(): Promise<void> {
    this.context = new AudioContext({ sampleRate: PLAYBACK_SAMPLE_RATE });
    // A browser may ignore the requested rate. If it does, playback drains
    // at the wrong speed and the audio either backs up or runs fast, so
    // this is worth knowing rather than assuming.
    this.actualSampleRate = this.context.sampleRate;
    await this.context.audioWorklet.addModule("/worklets/pcm-playback-processor.js");

    this.node = new AudioWorkletNode(this.context, "pcm-playback-processor", {
      numberOfInputs: 0,
      outputChannelCount: [1],
    });
    this.node.port.onmessage = (event) => {
      const data = event.data as { playing?: boolean; queuedSamples?: number };
      if (typeof data?.queuedSamples === "number") {
        this.queuedSeconds = data.queuedSamples / PLAYBACK_SAMPLE_RATE;
      }
      if (typeof data?.playing === "boolean") this.onSpeakingChange(data.playing);
    };

    // Analyser sits between the worklet and the speakers so the visualiser
    // reacts to the interviewer's actual voice, not a timer approximation.
    this.analyser = this.context.createAnalyser();
    this.analyser.fftSize = 256;
    this.amplitudeData = new Uint8Array(this.analyser.frequencyBinCount);

    this.node.connect(this.analyser);
    this.analyser.connect(this.context.destination);

    // Browsers start contexts suspended until a user gesture; the page only
    // calls this from a click, but resume() is harmless if already running.
    await this.context.resume().catch(() => {});
  }

  enqueue(base64Pcm: string): void {
    const buffer = fromBase64(base64Pcm);
    this.node?.port.postMessage(buffer, [buffer]);
  }

  /** Barge-in: drop everything still queued so the voice cuts immediately. */
  clear(): void {
    this.node?.port.postMessage("clear");
  }

  /** Seconds of audio received but not yet heard. A number that climbs is
   *  a backlog: the model answered long ago and we're still catching up. */
  backlogSeconds(): number {
    return this.queuedSeconds;
  }

  /** The rate the browser actually granted, vs PLAYBACK_SAMPLE_RATE. */
  sampleRate(): number {
    return this.actualSampleRate;
  }

  /** 0..1 loudness for the animated presence. */
  amplitude(): number {
    if (!this.analyser || !this.amplitudeData) return 0;
    // @ts-expect-error -- lib.dom types Uint8Array<ArrayBufferLike> here,
    // which doesn't match the ArrayBuffer-backed array at runtime.
    this.analyser.getByteTimeDomainData(this.amplitudeData);
    let peak = 0;
    for (let i = 0; i < this.amplitudeData.length; i++) {
      peak = Math.max(peak, Math.abs(this.amplitudeData[i] - 128));
    }
    return Math.min(1, peak / 128);
  }

  async stop(): Promise<void> {
    this.node?.port.close();
    this.node?.disconnect();
    this.analyser?.disconnect();
    await this.context?.close().catch(() => {});
    this.node = null;
    this.analyser = null;
    this.context = null;
  }
}
