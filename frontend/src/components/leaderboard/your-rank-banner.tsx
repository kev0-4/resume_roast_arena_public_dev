"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StampBadge } from "./stamp-badge";
import { useAuth } from "@/lib/auth-context";
import { getMyLeaderboardPosition, type MyLeaderboardPosition } from "@/lib/api";

// Only meaningful for a signed-in user (the leaderboard itself is public/
// anonymous-friendly, but "which entry is mine" needs a real identity) --
// renders nothing at all while signed out or still loading. Once signed
// in, always renders a card -- either the real position, or (no eligible
// roast yet) a "--" placeholder that doubles as a CTA to go get roasted,
// rather than disappearing entirely. A card that's just gone reads as
// broken; a card that says "you haven't been roasted yet" reads as
// intentional.
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
        // best-effort -- a failed lookup just means no real position to
        // show, falls back to the placeholder card below, not a broken
        // page
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
          Roast your resume to get on the board
        </span>
      </Link>
    );
  }

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
