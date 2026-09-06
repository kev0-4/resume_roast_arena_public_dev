"use client";

import { useEffect } from "react";
import Link from "next/link";
import { Home, RotateCcw } from "lucide-react";
import { Navbar } from "@/components/site/navbar";
import { stackedShadow } from "@/lib/text-shadow";

const HEADLINE_SHADOW = stackedShadow(10, "#001A99");

// Next.js's error boundary for anything under this route segment (root,
// so effectively the whole app) -- without it, any uncaught render-time
// error falls back to Next's default error screen instead of something
// on-theme. Must be a client component; `reset` re-renders the segment
// rather than a full page reload, so it can actually recover from a
// transient error, not just redirect away from it.
export default function ErrorBoundary({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // The one place in this app deliberately logging to the browser
    // console -- this is the last-resort catch-all, and losing the real
    // error with no trace anywhere would make an already-bad moment for
    // a user impossible to debug later.
    console.error("Unhandled error:", error);
  }, [error]);

  return (
    <div className="relative flex min-h-screen w-full flex-col overflow-hidden bg-brand-blue font-mono selection:bg-brand-lime selection:text-brand-blue">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />
      <Navbar />
      <main className="relative z-10 mx-auto flex w-full max-w-[1440px] flex-1 flex-col items-center justify-center px-4 pb-32 text-center">
        <span className="mb-4 font-display text-sm uppercase tracking-widest text-brand-lime">Error</span>
        <h1
          className="m-0 p-0 font-display text-[clamp(2.4rem,7vw,4.8rem)] uppercase leading-[0.9] tracking-tighter text-white"
          style={{ textShadow: HEADLINE_SHADOW }}
        >
          That broke, not you
        </h1>
        <p className="mt-4 max-w-md font-mono text-sm text-white/70">
          Something went wrong on our end. It&apos;s been logged -- try again, or head back home.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <button
            onClick={reset}
            className="flex items-center gap-2 rounded-full bg-brand-lime px-8 py-4 font-display text-sm uppercase tracking-wide text-black shadow-[4px_4px_0_#000] transition-all hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0_#000] md:text-base"
          >
            <RotateCcw size={18} strokeWidth={2.5} />
            Try again
          </button>
          <Link
            href="/"
            className="flex items-center gap-2 rounded-full border-2 border-white px-8 py-4 font-display text-sm uppercase tracking-wide text-white transition-colors hover:bg-white hover:text-brand-blue md:text-base"
          >
            <Home size={18} strokeWidth={2.5} />
            Home
          </Link>
        </div>
      </main>
    </div>
  );
}
