"use client";

// Orchestrates one real-time interview: the Gemini Live socket, mic capture,
// speaker playback, the running transcript, the clock, and scoring at the end.
//
// The page component stays presentational -- everything stateful and every
// teardown path lives here, because there are four things that must be shut
// down (socket, mic, player, timer) and half the ways this session can end
// are not button presses (clock expiry, socket drop, tab close).

import { useCallback, useEffect, useRef, useState } from "react";
import { MicCapture, PcmPlayer } from "@/lib/live-audio";
import { LiveInterviewSession } from "@/lib/live-session";
import {
  completeInterview,
  postTranscriptChunks,
  type InterviewScoreResult,
  type InterviewStartResponse,
  type TranscriptChunk,
  type TranscriptSpeaker,
} from "@/lib/interview-api";

export type InterviewPhase =
  | "greenroom" // mic not yet granted; waiting on the user's click
  | "connecting"
  | "live"
  | "ending" // flushing transcript
  | "scoring"
  | "done"
  | "error";

export interface TranscriptLine {
  id: number;
  speaker: TranscriptSpeaker;
  text: string;
}

/** How often finalised transcript lines are pushed to our backend. */
const FLUSH_INTERVAL_MS = 5000;

/** Cap on waiting for a closing line, so a stuck queue can't hang the room. */
const MAX_DRAIN_WAIT_MS = 12000;
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function useLiveInterview(start: InterviewStartResponse | null, getIdToken: () => Promise<string | null>) {
  const [phase, setPhase] = useState<InterviewPhase>("greenroom");
  const [error, setError] = useState<string | null>(null);
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  /** Unstable preview of what the candidate is saying right now. Rendered
   *  ghosted and replaced wholesale once the final version lands. */
  const [interim, setInterim] = useState("");
  const [speaking, setSpeaking] = useState(false);
  const [muted, setMuted] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [result, setResult] = useState<InterviewScoreResult | null>(null);
  /** Set when the INTERVIEWER ended the session rather than the candidate. */
  const [endedByInterviewer, setEndedByInterviewer] = useState<{ reason: string; category: string } | null>(null);
  /** Questions the candidate declined. Counts against the score. */
  const [skippedCount, setSkippedCount] = useState(0);
  /** Time from "connect" to the interviewer's first audio. The entire
   *  justification for this rebuild, so it is measured, not assumed. */
  const [firstAudioMs, setFirstAudioMs] = useState<number | null>(null);

  const sessionRef = useRef<LiveInterviewSession | null>(null);
  const micRef = useRef<MicCapture | null>(null);
  const playerRef = useRef<PcmPlayer | null>(null);
  const connectStartRef = useRef<number>(0);
  const gotAudioRef = useRef(false);

  // Transcript chunks that have been finalised but not yet sent upstream.
  const pendingRef = useRef<TranscriptChunk[]>([]);
  const seqRef = useRef(0);
  // Mirrored in refs because end() is called from socket callbacks that
  // captured an older render, and these must reach /complete accurately --
  // they are the negative marking.
  const skippedRef = useRef(0);
  const endedByInterviewerRef = useRef<{ reason: string; category: string } | null>(null);
  const speakingRef = useRef(false);
  // Guards the end sequence: clock expiry, socket close and the button can
  // all fire at once, and scoring must only ever run once.
  const endingRef = useRef(false);

  const flush = useCallback(async () => {
    if (!start || pendingRef.current.length === 0) return;
    const batch = pendingRef.current;
    pendingRef.current = [];
    try {
      const idToken = await getIdToken();
      if (!idToken) return;
      await postTranscriptChunks(start.interview_id, batch, idToken);
    } catch {
      // Put them back and retry on the next flush -- losing transcript is
      // worse than sending a chunk twice, and the server dedupes on seq.
      pendingRef.current = batch.concat(pendingRef.current);
    }
  }, [start, getIdToken]);

  /** Append a fragment to the running transcript, merging into the previous
   *  line when the same speaker is still talking. The Live API emits many
   *  small fragments per turn; one bubble per fragment would be unreadable. */
  const appendFragment = useCallback((speaker: TranscriptSpeaker, text: string) => {
    setLines((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.speaker === speaker) {
        const merged = [...prev];
        merged[merged.length - 1] = { ...last, text: last.text + text };
        return merged;
      }
      return [...prev, { id: prev.length, speaker, text }];
    });
    pendingRef.current.push({
      seq: seqRef.current++,
      speaker,
      text,
      is_final: true,
      at: new Date().toISOString(),
    });
  }, []);

  /**
   * Waits for the interviewer to stop talking, bounded.
   *
   * The initial pause exists because the closing line usually hasn't
   * STARTED playing when the tool call lands -- polling immediately would
   * see silence, conclude it had finished, and cut the line off.
   */
  const waitForPlaybackToDrain = useCallback(async () => {
    const startedAt = performance.now();
    await sleep(700);
    while (speakingRef.current && performance.now() - startedAt < MAX_DRAIN_WAIT_MS) {
      await sleep(150);
    }
  }, []);

  const teardown = useCallback(async () => {
    sessionRef.current?.close();
    sessionRef.current = null;
    await micRef.current?.stop();
    micRef.current = null;
    await playerRef.current?.stop();
    playerRef.current = null;
  }, []);

  /** The single end path. Every way an interview can finish routes here. */
  const end = useCallback(async () => {
    if (endingRef.current) return;
    endingRef.current = true;
    setPhase("ending");
    await teardown();
    await flush();

    setPhase("scoring");
    try {
      const idToken = await getIdToken();
      if (!idToken) {
        setError("Your session expired before we could score the interview.");
        setPhase("error");
        return;
      }
      if (!start) return;
      setResult(
        await completeInterview(start.interview_id, idToken, {
          skipped_questions: skippedRef.current,
          ended_early: endedByInterviewerRef.current ?? undefined,
        }),
      );
      setPhase("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not score the interview.");
      setPhase("error");
    }
  }, [start, teardown, flush, getIdToken, setResult]);

  // Held in a ref so the socket callbacks -- created once at connect time --
  // always call the current version rather than capturing a stale closure.
  const endRef = useRef(end);
  useEffect(() => {
    endRef.current = end;
  }, [end]);

  const connect = useCallback(async () => {
    if (!start) return;
    setPhase("connecting");
    setError(null);
    connectStartRef.current = performance.now();

    try {
      const player = new PcmPlayer((isSpeaking) => {
        speakingRef.current = isSpeaking;
        setSpeaking(isSpeaking);
      });
      await player.start();
      playerRef.current = player;

      const session = new LiveInterviewSession();
      sessionRef.current = session;

      await session.connect({
        token: start.token,
        model: start.model,
        systemInstruction: start.system_instruction,
        tools: start.tools,
        callbacks: {
          onOpen: () => setPhase("live"),
          onAudio: (b64) => {
            if (!gotAudioRef.current) {
              gotAudioRef.current = true;
              setFirstAudioMs(Math.round(performance.now() - connectStartRef.current));
            }
            playerRef.current?.enqueue(b64);
          },
          onTranscript: (speaker, text, isFinal) => {
            if (!isFinal) {
              setInterim(text);
              return;
            }
            if (speaker === "candidate") setInterim("");
            appendFragment(speaker, text);
          },
          // Barge-in: the user talked over the interviewer. Drop queued audio
          // so the voice cuts mid-word like a real interruption.
          onInterrupted: () => playerRef.current?.clear(),
          onToolCall: (calls) => {
            for (const call of calls) {
              if (call.name === "end_interview") {
                const ended = {
                  reason: String(call.args?.reason ?? ""),
                  category: String(call.args?.category ?? "COMPLETE"),
                };
                endedByInterviewerRef.current = ended;
                setEndedByInterviewer(ended);
                // Let the closing line finish before tearing the room down.
                // Verified against the real API that the tool call arrives
                // BEFORE the closing line has played, so ending immediately
                // would cut the interviewer off mid-sentence and read as a
                // crash rather than a decision it made.
                void (async () => {
                  await waitForPlaybackToDrain();
                  void endRef.current();
                })();
              } else if (call.name === "skip_question") {
                skippedRef.current += 1;
                setSkippedCount(skippedRef.current);
              }
            }
            // Must acknowledge, or the model waits on us and the room goes
            // silent at exactly the wrong moment.
            sessionRef.current?.respondToTool(calls, { ok: true });
          },
          onError: (message) => {
            setError(message);
            setPhase("error");
          },
          // A close mid-interview still counts as an interview -- score what
          // was said rather than stranding the row IN_PROGRESS forever.
          onClose: () => void endRef.current(),
        },
      });

      // Mic starts only after the socket is up, so the first words spoken
      // can't be captured into a void.
      const mic = new MicCapture((b64) => sessionRef.current?.sendAudio(b64));
      await mic.start();
      micRef.current = mic;

      // Only now ask the interviewer to open -- if it spoke before the mic
      // was live, an eager candidate could answer into a dead microphone.
      // Measured at ~0.6s from this call to its first audio.
      session.kickoff();
    } catch (err) {
      const message =
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Microphone access was blocked. Allow it in your browser, then start again."
          : err instanceof Error
            ? err.message
            : "Could not start the live session.";
      setError(message);
      setPhase("error");
      await teardown();
    }
  }, [start, appendFragment, teardown, waitForPlaybackToDrain]);

  const toggleMute = useCallback(() => {
    setMuted((prev) => {
      const next = !prev;
      micRef.current?.setMuted(next);
      // Tell the model the turn is over rather than leaving it waiting on
      // audio that will never arrive.
      if (next) sessionRef.current?.endAudioStream();
      return next;
    });
  }, []);

  // Countdown against the server's expiry, not a local 10:00 timer -- the
  // token dies on the server's clock regardless of what ours says.
  useEffect(() => {
    if (phase !== "live" || !start) return;
    const expiresAt = new Date(start.expires_at).getTime();
    const tick = () => {
      const left = Math.max(0, Math.round((expiresAt - Date.now()) / 1000));
      setSecondsLeft(left);
      if (left === 0) void endRef.current();
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [phase, start]);

  useEffect(() => {
    if (phase !== "live") return;
    const id = setInterval(() => void flush(), FLUSH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [phase, flush]);

  // Last resort for a closed tab: best-effort, and deliberately not relied
  // upon -- the 5s flush above is what actually keeps the transcript safe.
  useEffect(() => {
    const onHide = () => void flush();
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, [flush]);

  // Unmount (back button, route change) must not leave the mic light on.
  useEffect(() => () => void teardown(), [teardown]);

  return {
    phase,
    error,
    lines,
    interim,
    speaking,
    muted,
    secondsLeft,
    result,
    firstAudioMs,
    endedByInterviewer,
    skippedCount,
    connect,
    toggleMute,
    end,
    amplitude: () => playerRef.current?.amplitude() ?? 0,
  };
}
