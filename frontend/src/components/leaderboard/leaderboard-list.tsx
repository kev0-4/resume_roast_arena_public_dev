import { LeaderboardRow } from "./leaderboard-row";
import type { LeaderboardEntry } from "@/lib/api";

// One hard-shadow bordered card holding every row, hairline dividers
// between rows (not a shadow per row) -- see leaderboard-row.tsx's own
// comment for why.
export function LeaderboardList({ entries }: { entries: LeaderboardEntry[] }) {
  return (
    <div className="w-full overflow-hidden rounded-2xl border-[3px] border-black bg-white shadow-[5px_5px_0_#000]">
      {entries.map((entry) => (
        <LeaderboardRow key={entry.slug} entry={entry} />
      ))}
    </div>
  );
}
