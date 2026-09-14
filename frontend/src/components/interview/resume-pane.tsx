"use client";

// The in-room resume reference. Collapsed by default.
//
// This is the ANONYMIZED resume -- the same text the interviewer is
// working from, so both sides are demonstrably reading one document. It is
// deliberately not the roast: the roast names the exact weak spots the
// candidate is about to be challenged on, which would make the interview
// open-book.

import { useState } from "react";
import { FileText, X } from "lucide-react";

export function ResumePane({ resumeText }: { resumeText: string }) {
  const [open, setOpen] = useState(false);

  if (!resumeText.trim()) return null;

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="absolute bottom-4 right-4 z-20 flex items-center gap-2 rounded-full border-2 border-black bg-white px-4 py-2 shadow-[3px_3px_0_#000] transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[2px_2px_0_#000]"
      >
        <FileText size={14} strokeWidth={2.5} className="text-black/50" />
        <span className="font-mono text-[10px] font-black uppercase tracking-wide text-black">My resume</span>
      </button>
    );
  }

  return (
    // Overlays the stage rather than adding a third column: at phone width
    // a third column would leave nothing readable, and even on a laptop the
    // transcript matters more than the resume during a live answer.
    <div className="absolute inset-0 z-20 flex flex-col overflow-hidden rounded-[1.5rem] border-[3px] border-black bg-white shadow-[6px_6px_0_#000]">
      <div className="flex shrink-0 items-center justify-between border-b-[3px] border-black px-5 py-3">
        <p className="font-mono text-[11px] font-black uppercase tracking-wide text-black/50">
          Your resume &mdash; as the interviewer sees it
        </p>
        <button
          onClick={() => setOpen(false)}
          aria-label="Close resume"
          className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-black bg-white transition-colors hover:bg-black/5"
        >
          <X size={14} strokeWidth={3} />
        </button>
      </div>

      {/* Pre-wrap because the server sends the same [SECTION]-delimited
          plain text the model receives -- no markup to render. */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-black/80">
          {resumeText}
        </pre>
      </div>
    </div>
  );
}
