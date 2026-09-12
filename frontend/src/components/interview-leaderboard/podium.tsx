import { Trophy } from "lucide-react";
import { Avatar } from "@/components/leaderboard/avatar";
import type { InterviewLeaderboardEntry } from "@/lib/interview-api";

const PODIUM_ORDER = [1, 0, 2] as const; // visual left-to-right: #2, #1, #3
const BLOCK_HEIGHT: Record<number, number> = { 0: 132, 1: 96, 2: 76 };

// Duplicated from components/leaderboard/podium.tsx rather than
// parameterized -- see this directory's own README-in-comment reasoning
// in hero-panel.tsx. No StampBadge here: a 1-10 interview score has no
// SOLID/MID/ROASTED equivalent, so this version just doesn't render one
// rather than forcing an unrelated concept onto it. Also not a Link like
// the original -- interviews have no public/shareable link the way a
// roast's /r/{slug} does (InterviewLeaderboardEntry carries no slug at
// all, by design -- a transcript is real personal data, never public).
export function Podium({ entries }: { entries: InterviewLeaderboardEntry[] }) {
  const top3 = entries.slice(0, 3);
  if (top3.length === 0) return null;

  return (
    <div className="mx-auto flex max-w-md items-end justify-center gap-3 md:gap-5">
      {PODIUM_ORDER.filter((i) => top3[i]).map((i) => {
        const entry = top3[i];
        const isFirst = i === 0;
        return (
          <div key={`${entry.rank}-${entry.display_name}`} className="flex flex-1 flex-col items-center">
            <div className="mb-2 flex flex-col items-center">
              {isFirst && <Trophy size={22} className="mb-1 fill-brand-lime text-brand-lime" />}
              <Avatar name={entry.display_name} size={isFirst ? 56 : 44} />
              <p className="mt-2 max-w-[6.5rem] truncate text-center font-mono text-xs font-bold text-white">
                {entry.display_name}
              </p>
              <span className="font-display text-lg text-white md:text-xl">
                {entry.score}
                <span className="text-xs text-white/50">/10</span>
              </span>
            </div>
            <div
              className="flex w-full items-start justify-center rounded-t-xl border-2 border-b-0 border-black pt-2"
              style={{ height: BLOCK_HEIGHT[i], background: isFirst ? "var(--brand-lime)" : "#ffffff" }}
            >
              <span className="font-display text-2xl text-black md:text-3xl">#{entry.rank}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
