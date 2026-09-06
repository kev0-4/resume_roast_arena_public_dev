import Link from "next/link";
import { Trophy } from "lucide-react";
import { StampBadge } from "./stamp-badge";
import { Avatar } from "./avatar";
import type { LeaderboardEntry } from "@/lib/api";

const PODIUM_ORDER = [1, 0, 2] as const; // visual left-to-right: #2, #1, #3
const BLOCK_HEIGHT: Record<number, number> = { 0: 132, 1: 96, 2: 76 };

export function Podium({ entries }: { entries: LeaderboardEntry[] }) {
  const top3 = entries.slice(0, 3);
  if (top3.length === 0) return null;

  return (
    <div className="relative w-full max-w-2xl overflow-hidden rounded-[2rem] bg-brand-blue-deep px-6 pb-6 pt-10 md:pt-12">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      <div className="relative z-10 mx-auto flex items-end justify-center gap-3 md:gap-5">
        {PODIUM_ORDER.filter((i) => top3[i]).map((i) => {
          const entry = top3[i];
          const isFirst = i === 0;
          return (
            <Link key={entry.slug} href={`/r/${entry.slug}`} className="group flex flex-1 flex-col items-center">
              <div className="mb-2 flex flex-col items-center">
                {isFirst && <Trophy size={22} className="mb-1 fill-brand-lime text-brand-lime" />}
                <Avatar name={entry.display_name} size={isFirst ? 56 : 44} />
                <p className="mt-2 max-w-[6.5rem] truncate text-center font-mono text-xs font-bold text-white">
                  {entry.display_name}
                </p>
                <span className="font-display text-lg text-white md:text-xl">{entry.composite_score}</span>
                <div className="mt-1">
                  <StampBadge stamp={entry.stamp} />
                </div>
              </div>
              <div
                className="flex w-full items-start justify-center rounded-t-xl border-2 border-b-0 border-black pt-2 transition-transform group-hover:-translate-y-1"
                style={{ height: BLOCK_HEIGHT[i], background: isFirst ? "var(--brand-lime)" : "#ffffff" }}
              >
                <span className="font-display text-2xl text-black md:text-3xl">#{entry.rank}</span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
