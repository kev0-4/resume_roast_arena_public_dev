import Link from "next/link";
import { ChevronRight, Clock } from "lucide-react";
import { StampBadge } from "./stamp-badge";
import { Avatar } from "./avatar";
import { relativeTime } from "@/lib/relative-time";
import type { LeaderboardEntry } from "@/lib/api";

// A single row within the shared bordered-card list (leaderboard-list.tsx)
// -- not its own card. With 50+ rows a shadow-per-row reads as noise
// rather than a leaderboard; the chunky brand language stays on the
// accents (stamp badge, the list's own outer card) instead.
export function LeaderboardRow({ entry }: { entry: LeaderboardEntry }) {
  return (
    <Link
      href={`/r/${entry.slug}`}
      className="group flex items-center gap-3 border-b border-black/8 px-3 py-3 transition-colors last:border-0 hover:bg-black/[0.02] md:gap-4 md:px-4"
    >
      <span className="w-7 flex-shrink-0 text-center font-display text-sm tabular-nums text-black/40">
        {entry.rank}
      </span>
      <Avatar name={entry.display_name} />
      <div className="min-w-0 flex-1">
        <p className="truncate font-mono text-[13.5px] font-bold text-black">{entry.display_name}</p>
        <p className="mt-0.5 flex items-center gap-1 font-mono text-[10.5px] font-semibold text-black/40">
          <Clock size={10} />
          {relativeTime(entry.created_at)}
        </p>
      </div>
      <span className="flex-shrink-0 font-display text-base tabular-nums text-black">{entry.composite_score}</span>
      <StampBadge stamp={entry.stamp} className="hidden flex-shrink-0 sm:inline-flex" />
      <ChevronRight
        size={16}
        className="flex-shrink-0 text-black/20 transition-all group-hover:translate-x-0.5 group-hover:text-black/40"
      />
    </Link>
  );
}
