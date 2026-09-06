"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, RotateCcw } from "lucide-react";
import { Navbar } from "@/components/site/navbar";
import { stackedShadow } from "@/lib/text-shadow";
import { getSessionStatus, publicRoastCardUrl, SessionStatus, SessionStatusResponse } from "@/lib/api";

const HEADLINE_SHADOW = stackedShadow(10, "#001A99");

// Real backend pipeline stages (backend/src/db/sessions.py JobStatusEnum)
// mapped to on-brand flavor text -- reflects the session's actual current
// status on every poll, not a fake canned animation.
const STATUS_COPY: Record<SessionStatus, string> = {
  UPLOADED: "Picking up your resume...",
  QUEUED: "Queued up...",
  PROCESSING: "Reading your resume...",
  EXTRACTED: "Reading your resume...",
  NORMALIZING: "Making sense of the mess...",
  NORMALIZED: "Making sense of the mess...",
  ANONYMIZING: "Redacting your identity...",
  ANONYMIZED: "Redacting your identity...",
  SCORING: "Judging your bullet points...",
  SCORED: "Judging your bullet points...",
  ROASTING: "Writing the roast...",
  ROASTED: "Writing the roast...",
  RENDERING: "Plating the roast...",
  DONE: "Done.",
  FAILED: "That didn't work.",
};

const POLL_INTERVAL_MS = 2000;

export default function ProcessingPage() {
  const params = useParams<{ sessionId: string }>();
  const router = useRouter();
  const [session, setSession] = useState<SessionStatusResponse | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const result = await getSessionStatus(params.sessionId);
        if (cancelled) return;
        setSession(result);
        setPollError(null);
        if (result.status === "DONE" || result.status === "FAILED") {
          if (intervalRef.current) clearInterval(intervalRef.current);
        }
      } catch {
        if (!cancelled) setPollError("Lost connection to the server -- retrying...");
      }
    };

    poll();
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [params.sessionId]);

  const status = session?.status;
  const isTerminal = status === "DONE" || status === "FAILED";

  return (
    <div className="relative flex min-h-screen w-full flex-col overflow-hidden bg-brand-blue font-mono selection:bg-brand-lime selection:text-brand-blue">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      <Navbar />

      <main className="relative z-10 mx-auto flex w-full max-w-[1440px] flex-1 flex-col items-center justify-center px-4 pb-32 text-center">
        {status === "FAILED" ? (
          <>
            <h1
              className="m-0 p-0 font-display text-[clamp(2.4rem,7vw,4.8rem)] uppercase leading-[0.9] tracking-tighter text-white"
              style={{ textShadow: HEADLINE_SHADOW }}
            >
              That didn&apos;t work
            </h1>
            <p className="mt-4 max-w-md font-mono text-sm text-white/70">
              {session?.error_message ?? "Something went wrong processing your resume."}
            </p>
            <Link
              href="/roast"
              className="mt-8 flex items-center gap-2 rounded-full bg-brand-lime px-8 py-4 font-display text-sm uppercase tracking-wide text-black shadow-[4px_4px_0_#000] transition-all hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0_#000] md:text-base"
            >
              <RotateCcw size={18} strokeWidth={2.5} />
              Try again
            </Link>
          </>
        ) : status === "DONE" && session?.slug ? (
          <>
            <h1
              className="m-0 p-0 font-display text-[clamp(2.4rem,7vw,4.8rem)] uppercase leading-[0.9] tracking-tighter text-brand-lime"
              style={{ textShadow: HEADLINE_SHADOW }}
            >
              Your roast is ready
            </h1>
            <a
              href={publicRoastCardUrl(session.slug)}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-8 flex items-center gap-2 rounded-full bg-brand-lime px-8 py-4 font-display text-sm uppercase tracking-wide text-black shadow-[4px_4px_0_#000] transition-all hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0_#000] md:text-base"
            >
              View your roast card
              <ArrowRight size={18} strokeWidth={2.5} />
            </a>
            <button
              onClick={() => router.push("/roast")}
              className="mt-4 font-mono text-xs font-semibold text-white/60 underline-offset-4 hover:text-white hover:underline"
            >
              Roast another resume
            </button>
          </>
        ) : (
          <>
            <div className="mb-8 h-14 w-14 animate-spin rounded-full border-4 border-white/20 border-t-brand-lime" />
            <h1
              className="m-0 p-0 font-display text-[clamp(2rem,6vw,3.6rem)] uppercase leading-[0.9] tracking-tighter text-white"
              style={{ textShadow: HEADLINE_SHADOW }}
            >
              {status ? STATUS_COPY[status] : "Getting started..."}
            </h1>
            <p className="mt-4 font-mono text-xs text-white/50">
              This takes a minute -- an actual AI is actually reading your resume.
            </p>
          </>
        )}

        {pollError && !isTerminal && (
          <p className="mt-6 font-mono text-xs font-semibold text-brand-lime">{pollError}</p>
        )}
      </main>
    </div>
  );
}
