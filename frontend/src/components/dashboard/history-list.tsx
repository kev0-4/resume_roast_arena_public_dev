import { HistoryRow } from "./history-row";
import type { MySession } from "@/lib/api";

// Same hard-shadow bordered card + hairline dividers as the leaderboard's
// own list (leaderboard-list.tsx) -- kept as a separate component since
// it renders MySession rows, not LeaderboardEntry rows, but intentionally
// matching that visual language for consistency across the two "list of
// roasts" surfaces in this app.
export function HistoryList({ sessions }: { sessions: MySession[] }) {
  return (
    <div className="w-full overflow-hidden rounded-2xl border-[3px] border-black bg-white shadow-[5px_5px_0_#000]">
      {sessions.map((session) => (
        <HistoryRow key={session.session_id} session={session} />
      ))}
    </div>
  );
}
