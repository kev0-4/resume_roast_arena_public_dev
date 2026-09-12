"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { getMyInterviewLeaderboardPosition, type MyInterviewLeaderboardPosition } from "@/lib/interview-api";

// Duplicated from components/leaderboard/your-rank-banner.tsx -- same
// signed-out-renders-nothing / no-eligible-interview-yet-shows-a-
// placeholder-CTA behavior, pointed at /roast (the only entry point into
// ever getting an interview at all) since there's no interview-specific
// starting point of its own.
export function YourRankBanner() {
  const { firebaseUser, getIdToken } = useAuth();
  const [position, setPosition] = useState<MyInterviewLeaderboardPosition | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!firebaseUser) return;
    let cancelled = false;
    (async () => {
      try {
        const token = await getIdToken();
        if (!token) return;
        const result = await getMyInterviewLeaderboardPosition(token);
        if (!cancelled) setPosition(result);
      } catch {
        // best-effort -- falls back to the placeholder card below
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [firebaseUser, getIdToken]);

  if (!firebaseUser || !loaded) return null;

  if (!position) {
    return (
      <Link
        href="/roast"
        className="flex w-full max-w-2xl items-center gap-4 rounded-2xl border-[3px] border-black bg-white/90 px-5 py-3 shadow-[5px_5px_0_#000] transition-transform hover:-translate-y-0.5"
      >
        <span className="font-mono text-[10px] font-black uppercase tracking-wide text-black/40">Your rank</span>
        <span className="font-display text-lg text-black/30">--</span>
        <span className="ml-auto font-mono text-xs font-semibold text-black/50">
          Get roasted, then interview to get on the board
        </span>
      </Link>
    );
  }

  return (
    <div className="flex w-full max-w-2xl items-center gap-4 rounded-2xl border-[3px] border-black bg-brand-lime px-5 py-3 shadow-[5px_5px_0_#000]">
      <span className="font-mono text-[10px] font-black uppercase tracking-wide text-black/60">Your rank</span>
      <span className="font-display text-lg text-black">#{position.rank}</span>
      <span className="font-mono text-xs font-semibold text-black/50">of {position.total}</span>
      <span className="ml-auto font-display text-black">
        {position.score}
        <span className="text-xs text-black/40">/10</span>
      </span>
    </div>
  );
}
