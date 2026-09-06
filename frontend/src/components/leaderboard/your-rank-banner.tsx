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
      className="flex w-full max-w-3xl items-center gap-4 rounded-2xl border border-brand-lime/40 bg-black/60 px-5 py-3 backdrop-blur-md transition-colors hover:border-brand-lime/70"
    >
      <span className="font-mono text-[10px] font-semibold uppercase tracking-wide text-white/50">Your rank</span>
      <span className="font-display text-lg text-brand-lime">#{position.rank}</span>
      <span className="font-mono text-xs text-white/50">of {position.total}</span>
      <StampBadge stamp={position.stamp} className="ml-auto" />
      <span className="font-display text-white">
        {position.composite_score}
        <span className="text-xs text-white/40">/100</span>
      </span>
    </Link>
  );
}
