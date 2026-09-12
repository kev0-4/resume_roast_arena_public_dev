"use client";

// The live transcript rail. Both sides of the conversation are transcribed
// by the Live API itself (inputAudioTranscription / outputAudioTranscription),
// so this is the model's own record of what was said -- not a second
// speech-to-text pass we'd have to pay for and reconcile.

import { useEffect, useRef } from "react";
import type { TranscriptLine } from "@/hooks/use-live-interview";

export function TranscriptPane({ lines, interim }: { lines: TranscriptLine[]; interim: string }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Follow the conversation. `block: "end"` keeps the pane itself scrolling
  // without dragging the whole page around it.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [lines, interim]);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-[1.5rem] border-[3px] border-black bg-white shadow-[6px_6px_0_#000]">
      <div className="shrink-0 border-b-[3px] border-black px-5 py-3">
        <p className="font-mono text-[11px] font-black uppercase tracking-wide text-black/50">Live transcript</p>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
        {lines.length === 0 && !interim ? (
          <p className="font-mono text-xs text-black/35">
            The interviewer opens. Everything either of you says lands here as it&apos;s said.
          </p>
        ) : null}

        {lines.map((line) => (
          <div key={line.id}>
            <p
              className={[
                "mb-1 font-mono text-[10px] font-black uppercase tracking-wide",
                line.speaker === "interviewer" ? "text-brand-blue" : "text-black/40",
              ].join(" ")}
            >
              {line.speaker === "interviewer" ? "Interviewer" : "You"}
            </p>
            <p
              className={[
                "font-mono text-sm leading-relaxed",
                line.speaker === "interviewer"
                  ? "rounded-xl rounded-tl-sm bg-brand-blue/[0.06] px-3 py-2 text-black"
                  : "text-black/75",
              ].join(" ")}
            >
              {line.text}
            </p>
          </div>
        ))}

        {/* Unstable preview of the current utterance -- ghosted so it reads
            as "still being heard" rather than as settled transcript. */}
        {interim ? (
          <div>
            <p className="mb-1 font-mono text-[10px] font-black uppercase tracking-wide text-black/40">You</p>
            <p className="font-mono text-sm italic leading-relaxed text-black/35">{interim}</p>
          </div>
        ) : null}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
