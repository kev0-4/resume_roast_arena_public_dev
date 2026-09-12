// Thin wrapper around @google/genai's Live API session for the interview.
//
// The browser holds this WebSocket directly to Gemini, authenticated with a
// single-use ephemeral token minted by our backend -- our API key never
// reaches the client, and there's no relay hop to add latency.

import { GoogleGenAI, Modality, ThinkingLevel, type Session } from "@google/genai";
import { MIC_MIME_TYPE } from "./live-audio";

export interface LiveSessionCallbacks {
  onAudio: (base64Pcm: string) => void;
  /** A transcript fragment. `speaker` says whose voice it was. */
  onTranscript: (speaker: "interviewer" | "candidate", text: string, isFinal: boolean) => void;
  /** User talked over the interviewer -- drop queued audio immediately. */
  onInterrupted: () => void;
  onOpen: () => void;
  onClose: (reason: string) => void;
  onError: (message: string) => void;
}

export class LiveInterviewSession {
  private session: Session | null = null;

  async connect(opts: {
    token: string;
    model: string;
    systemInstruction: string;
    callbacks: LiveSessionCallbacks;
  }): Promise<void> {
    const { token, model, systemInstruction, callbacks } = opts;

    // apiVersion v1alpha is REQUIRED for ephemeral tokens -- the SDK warns
    // about this explicitly and otherwise builds the wrong WebSocket path.
    // (Verified by reading @google/genai's own web build.)
    const ai = new GoogleGenAI({
      apiKey: token,
      httpOptions: { apiVersion: "v1alpha" },
    });

    this.session = await ai.live.connect({
      model,
      config: {
        // AUDIO only -- the API allows TEXT or AUDIO per session, never
        // both. Text still arrives, via the transcription configs below.
        responseModalities: [Modality.AUDIO],
        systemInstruction: { parts: [{ text: systemInstruction }] },
        inputAudioTranscription: {},
        outputAudioTranscription: {},
        // Lowest latency, which is the entire point of this rebuild.
        // NOTE: proactivity and enableAffectiveDialog are NOT supported on
        // gemini-3.1-flash-live-preview -- Google's reference says to omit
        // them, and sending them errors the session.
        thinkingConfig: { thinkingLevel: ThinkingLevel.MINIMAL },
      },
      callbacks: {
        onopen: () => callbacks.onOpen(),
        onmessage: (message) => {
          const content = message.serverContent;
          if (!content) return;

          // A single event can carry several parts at once (audio AND a
          // transcript fragment), so every branch below must be checked --
          // not else-if'd.
          if (content.modelTurn?.parts) {
            for (const part of content.modelTurn.parts) {
              const data = part.inlineData?.data;
              if (data) callbacks.onAudio(data);
            }
          }
          if (content.inputTranscription?.text) {
            callbacks.onTranscript("candidate", content.inputTranscription.text, true);
          }
          const interim = (content as { interimInputTranscription?: { text?: string } })
            .interimInputTranscription;
          if (interim?.text) {
            callbacks.onTranscript("candidate", interim.text, false);
          }
          if (content.outputTranscription?.text) {
            callbacks.onTranscript("interviewer", content.outputTranscription.text, true);
          }
          if (content.interrupted) callbacks.onInterrupted();
        },
        onerror: (e: ErrorEvent) => callbacks.onError(e.message || "Live connection error"),
        onclose: (e: CloseEvent) => callbacks.onClose(e.reason || "closed"),
      },
    });
  }

  /**
   * Makes the interviewer open the conversation.
   *
   * This is required, and finding that out took probing the real API. A
   * system instruction telling the model to "open the interview yourself,
   * immediately" is NOT enough: connected and left alone the model says
   * nothing at all, and a second of silence on the mic doesn't wake it
   * either. Both were measured -- twenty seconds of dead air, zero audio
   * chunks. Without this seed the candidate joins and sits in silence,
   * waiting for an interviewer that is itself waiting for them.
   *
   * The seed is a text turn rather than audio because it costs nothing to
   * send and never reaches the transcript: only spoken audio produces
   * inputTranscription, so this line stays out of what gets scored.
   */
  kickoff(): void {
    this.session?.sendClientContent({
      turns: [{ role: "user", parts: [{ text: "I'm here and ready. Please begin the interview." }] }],
      turnComplete: true,
    });
  }

  sendAudio(base64Pcm: string): void {
    // sendRealtimeInput for the live mic stream -- it's the streaming
    // path, and unlike sendClientContent it doesn't commit a turn on
    // every call.
    this.session?.sendRealtimeInput({
      audio: { data: base64Pcm, mimeType: MIC_MIME_TYPE },
    });
  }

  /** Flush cached audio when the mic goes quiet or muted. */
  endAudioStream(): void {
    this.session?.sendRealtimeInput({ audioStreamEnd: true });
  }

  close(): void {
    try {
      this.session?.close();
    } catch {
      // Already closed/closing -- nothing useful to do.
    }
    this.session = null;
  }
}
