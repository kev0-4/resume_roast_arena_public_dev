"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { RotateCcw } from "lucide-react";
import { Navbar } from "@/components/site/navbar";
import { ProcessingStages } from "@/components/roast/processing-stages";
import { stackedShadow } from "@/lib/text-shadow";
import { getSessionStatus, SessionStatusResponse } from "@/lib/api";

const HEADLINE_SHADOW = stackedShadow(10, "#001A99");
const POLL_INTERVAL_MS = 2000;

const VIEW_TRANSITION = {
  initial: { opacity: 0, y: 16, scale: 0.98 },
  animate: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: -16, scale: 0.98 },
  transition: { duration: 0.4, ease: "easeOut" as const },
};

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
        if (result.status === "DONE" && result.slug) {
          router.push(`/r/${result.slug}`);
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
  }, [params.sessionId, router]);

  const status = session?.status;
  const isTerminal = status === "DONE" || status === "FAILED";
  const view = status === "FAILED" ? "failed" : status === "DONE" && session?.slug ? "done" : "processing";

  return (
    <div className="relative flex min-h-screen w-full flex-col overflow-hidden bg-brand-blue font-mono selection:bg-brand-lime selection:text-brand-blue">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      <Navbar />

      <main className="relative z-10 mx-auto flex w-full max-w-[1440px] flex-1 flex-col items-center justify-center px-4 pb-32 text-center">
        <AnimatePresence mode="wait">
          {view === "failed" ? (
            <motion.div key="failed" {...VIEW_TRANSITION} className="flex flex-col items-center">
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
            </motion.div>
          ) : view === "done" ? (
            <motion.div key="done" {...VIEW_TRANSITION} className="flex flex-col items-center">
              <h1
                className="m-0 p-0 font-display text-[clamp(2.4rem,7vw,4.8rem)] uppercase leading-[0.9] tracking-tighter text-brand-lime"
                style={{ textShadow: HEADLINE_SHADOW }}
              >
                Your roast is ready
              </h1>
              <p className="mt-4 font-mono text-xs text-white/60">Taking you there now...</p>
            </motion.div>
          ) : (
            <motion.div key="processing" {...VIEW_TRANSITION}>
              <ProcessingStages status={status} />
            </motion.div>
          )}
        </AnimatePresence>

        {pollError && !isTerminal && (
          <p className="mt-6 font-mono text-xs font-semibold text-brand-lime">{pollError}</p>
        )}
      </main>
    </div>
  );
}
