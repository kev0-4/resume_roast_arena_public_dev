import Link from "next/link";
import { StampBadge } from "./stamp-badge";
import { relativeTime } from "@/lib/relative-time";
import type { LeaderboardEntry } from "@/lib/api";

export function LeaderboardRow({ entry }: { entry: LeaderboardEntry }) {
  return (
    <Link
      href={`/r/${entry.slug}`}
      className="flex items-center gap-4 rounded-2xl border border-black/10 bg-white px-4 py-3 transition-colors hover:border-brand-blue/30 hover:bg-brand-blue/5"
    >
      <span className="w-8 flex-shrink-0 text-center font-display text-sm text-black/40">#{entry.rank}</span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-mono text-sm font-semibold text-black">{entry.display_name}</p>
        <p className="font-mono text-[11px] text-black/40">{relativeTime(entry.created_at)}</p>
      </div>
      <StampBadge stamp={entry.stamp} variant="light" className="hidden sm:inline-block" />
      <span className="flex-shrink-0 font-display text-lg text-black">
        {entry.composite_score}
        <span className="text-xs text-black/40">/100</span>
      </span>
    </Link>
  );
}
