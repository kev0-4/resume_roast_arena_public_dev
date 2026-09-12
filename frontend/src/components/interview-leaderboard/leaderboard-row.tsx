import { Clock } from "lucide-react";
import { Avatar } from "@/components/leaderboard/avatar";
import { relativeTime } from "@/lib/relative-time";
import type { InterviewLeaderboardEntry } from "@/lib/interview-api";

// Duplicated from components/leaderboard/leaderboard-row.tsx. Not a Link
// (no per-entry public page to send someone to -- see podium.tsx's own
// note on this), so no chevron/hover-affordance either.
export function LeaderboardRow({ entry }: { entry: InterviewLeaderboardEntry }) {
  return (
    <div className="flex items-center gap-3 border-b border-black/8 px-3 py-3 last:border-0 md:gap-4 md:px-4">
      <span className="w-7 flex-shrink-0 text-center font-display text-sm tabular-nums text-black/40">
        {entry.rank}
      </span>
      <Avatar name={entry.display_name} />
      <div className="min-w-0 flex-1">
        <p className="truncate font-mono text-[13.5px] font-bold text-black">{entry.display_name}</p>
        <p className="mt-0.5 flex items-center gap-1 font-mono text-[10.5px] font-semibold text-black/40">
          <Clock size={10} />
          {relativeTime(entry.completed_at)}
        </p>
      </div>
      <span className="flex-shrink-0 font-display text-base tabular-nums text-black">
        {entry.score}
        <span className="text-xs text-black/40">/10</span>
      </span>
    </div>
  );
}
