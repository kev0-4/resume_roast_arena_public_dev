"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StampBadge } from "./stamp-badge";
import { useAuth } from "@/lib/auth-context";
import { getMyLeaderboardPosition, type MyLeaderboardPosition } from "@/lib/api";

// Only meaningful for a signed-in user (the leaderboard itself is public/
// anonymous-friendly, but "which entry is mine" needs a real identity) --
// renders nothing at all while signed out rather than a sign-in prompt,
// so it doesn't compete with the page's own header for attention.
export function YourRankBanner() {
  const { firebaseUser, getIdToken } = useAuth();
  const [position, setPosition] = useState<MyLeaderboardPosition | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    // No synchronous reset for the signed-out case -- the render guard
    // below already returns null whenever !firebaseUser, so a stale
    // position/loaded value from a previous sign-in is never shown; the
    // only setState calls that matter are the ones inside the async
    // fetch below.
    if (!firebaseUser) return;
    let cancelled = false;
    (async () => {
      try {
        const token = await getIdToken();
        if (!token) return;
        const result = await getMyLeaderboardPosition(token);
        if (!cancelled) setPosition(result);
      } catch {
        // best-effort -- a failed lookup just means no banner, not a
        // broken page
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [firebaseUser, getIdToken]);

  if (!firebaseUser || !loaded || !position) return null;

  return (
    <Link
      href={`/r/${position.slug}`}
      className="group flex w-full max-w-2xl items-center gap-4 rounded-2xl border-[3px] border-black bg-brand-lime px-5 py-3 shadow-[5px_5px_0_#000] transition-transform hover:-translate-y-0.5"
    >
      <span className="font-mono text-[10px] font-black uppercase tracking-wide text-black/60">Your rank</span>
      <span className="font-display text-lg text-black">#{position.rank}</span>
      <span className="font-mono text-xs font-semibold text-black/50">of {position.total}</span>
      <StampBadge stamp={position.stamp} className="ml-auto" />
      <span className="font-display text-black">
        {position.composite_score}
        <span className="text-xs text-black/40">/100</span>
      </span>
    </Link>
  );
}
