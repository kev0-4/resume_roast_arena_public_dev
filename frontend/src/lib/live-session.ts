// Thin wrapper around @google/genai's Live API session for the interview.
//
// The browser holds this WebSocket directly to Gemini, authenticated with a
// single-use ephemeral token minted by our backend -- our API key never
// reaches the client, and there's no relay hop to add latency.

import { GoogleGenAI, Modality, ThinkingLevel, type Session } from "@google/genai";
import { MIC_MIME_TYPE } from "./live-audio";

/** A tool the interviewer invoked. See backend/src/interview/tools.py. */
export interface LiveToolCall {
  id?: string;
  name?: string;
  args?: Record<string, unknown>;
}

export interface LiveSessionCallbacks {
  onAudio: (base64Pcm: string) => void;
  /** A transcript fragment. `speaker` says whose voice it was. */
  onTranscript: (speaker: "interviewer" | "candidate", text: string, isFinal: boolean) => void;
  /** User talked over the interviewer -- drop queued audio immediately. */
  onInterrupted: () => void;
  /** The interviewer chose to end the session or skip a question. */
  onToolCall: (calls: LiveToolCall[]) => void;
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
    /** Passed straight through from the server; see tools.py. */
    tools: unknown[];
    callbacks: LiveSessionCallbacks;
  }): Promise<void> {
    const { token, model, systemInstruction, tools, callbacks } = opts;

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
        // Sent for parity with what's pinned into the token. The token's
        // copy is the authoritative one.
        tools: tools as never,
      },
      callbacks: {
        onopen: () => callbacks.onOpen(),
        onmessage: (message) => {
          // Tool calls arrive as their own top-level message, NOT inside
          // serverContent -- confirmed by dumping the raw stream. Handling
          // it after an early `return` on serverContent would silently
          // swallow every one of them.
          if (message.toolCall?.functionCalls?.length) {
            callbacks.onToolCall(message.toolCall.functionCalls as LiveToolCall[]);
          }

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
        // Logged as well as surfaced: a close or error mid-interview is the
        // single most useful line in the log when the room goes quiet, and
        // the UI path for it can itself be what's broken.
        onerror: (e: ErrorEvent) => {
          console.error("[interview] live socket error:", e.message);
          callbacks.onError(e.message || "Live connection error");
        },
        onclose: (e: CloseEvent) => {
          console.warn(`[interview] live socket closed: code=${e.code} reason=${e.reason || "(none)"}`);
          callbacks.onClose(e.reason || "closed");
        },
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

  /**
   * A text turn attributed to the candidate, outside the mic path.
   *
   * Not wired to any UI -- the product is voice-only by design. Exists
   * for scripts/interview_smoke_test's Playwright runner (see the
   * dev-only hook in use-live-interview.ts): the actual audio-in path
   * was exhaustively verified, in both this SDK and a hand-rolled Python
   * client, to never produce input_transcription for REPLAYED audio
   * (TTS or a real recorded voice, from a real mic or Chrome's fake
   * device) -- while `sendClientContent` text turns reliably work every
   * time. That gap points at something about live-captured-vs-replayed
   * audio, not at this method; text stays the one reliable way to drive
   * begin_round/end_interview from outside a real live conversation.
   */
  sendText(text: string): void {
    this.session?.sendClientContent({
      turns: [{ role: "user", parts: [{ text }] }],
      turnComplete: true,
    });
  }

  /**
   * Acknowledges a tool call. Required for skip_question: the model waits
   * for the response before continuing, so without this the interview
   * stalls in silence right after agreeing to move on -- the exact moment
   * the candidate is least forgiving of dead air.
   */
  respondToTool(calls: LiveToolCall[], response: Record<string, unknown>): void {
    this.session?.sendToolResponse({
      functionResponses: calls.map((call) => ({ id: call.id, name: call.name, response })),
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
