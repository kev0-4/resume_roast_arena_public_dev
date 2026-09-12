import { LeaderboardRow } from "./leaderboard-row";
import type { InterviewLeaderboardEntry } from "@/lib/interview-api";

// Duplicated from components/leaderboard/leaderboard-list.tsx -- pure
// layout wrapper, trivial either way, kept alongside its own
// interview-specific LeaderboardRow for consistency with the rest of this
// directory.
export function LeaderboardList({ entries }: { entries: InterviewLeaderboardEntry[] }) {
  return (
    <div className="w-full overflow-hidden rounded-2xl border-[3px] border-black bg-white shadow-[5px_5px_0_#000]">
      {entries.map((entry) => (
        <LeaderboardRow key={`${entry.rank}-${entry.display_name}`} entry={entry} />
      ))}
    </div>
  );
}
