"use client";

import { useRef, useState } from "react";
import { Mic, Square } from "lucide-react";

// Chrome defaults to audio/webm;codecs=opus, Safari often only supports
// audio/mp4 -- try in preference order, first isTypeSupported() match
// wins. Confirmed against the real Gemini audio-input call (backend
// smoke test) that webm/opus works; mp4 is the fallback for browsers
// that never offer webm at all, not independently verified against
// Gemini yet -- flagged as a real-browser risk in the plan.
const CANDIDATE_MIME_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];

function pickSupportedMimeType(): string | null {
  if (typeof MediaRecorder === "undefined") return null;
  for (const type of CANDIDATE_MIME_TYPES) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return null;
}

export function RecorderButton({
  disabled,
  onRecordingComplete,
}: {
  disabled?: boolean;
  onRecordingComplete: (blob: Blob, mimeType: string) => void;
}) {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  const startRecording = async () => {
    setError(null);
    const mimeType = pickSupportedMimeType();
    if (!mimeType) {
      setError("Your browser can't record audio -- try a different browser.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType });
        stopStream();
        onRecordingComplete(blob, mimeType);
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch {
      setError("Couldn't access your microphone -- check your browser's permission settings.");
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  };

  return (
    <div className="flex flex-col items-center gap-3">
      <button
        disabled={disabled}
        onClick={recording ? stopRecording : startRecording}
        className={[
          "flex h-20 w-20 items-center justify-center rounded-full border-[3px] border-black shadow-[4px_4px_0_#000] transition-all md:h-24 md:w-24",
          disabled
            ? "cursor-not-allowed bg-black/10 text-black/30"
            : recording
              ? "animate-pulse bg-red-500 text-white hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0_#000]"
              : "bg-brand-lime text-black hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0_#000]",
        ].join(" ")}
        aria-label={recording ? "Stop recording" : "Start recording your answer"}
      >
        {recording ? <Square size={28} fill="currentColor" /> : <Mic size={32} />}
      </button>
      <p className="font-mono text-xs font-semibold uppercase tracking-wide text-black/50">
        {recording ? "Recording -- tap to stop" : disabled ? "Listen first" : "Tap to answer"}
      </p>
      {error && <p className="max-w-xs text-center font-mono text-xs font-semibold text-red-600">{error}</p>}
    </div>
  );
}
