import Link from "next/link";
import { Crown } from "lucide-react";
import { StampBadge } from "./stamp-badge";
import type { LeaderboardEntry } from "@/lib/api";

const PODIUM_ORDER = [1, 0, 2] as const; // visual left-to-right: #2, #1, #3
const HEIGHT: Record<number, string> = { 0: "md:pt-0", 1: "md:pt-10", 2: "md:pt-14" };

export function Podium({ entries }: { entries: LeaderboardEntry[] }) {
  const top3 = entries.slice(0, 3);
  if (top3.length === 0) return null;

  return (
    <div className="grid w-full max-w-3xl grid-cols-1 gap-4 md:grid-cols-3 md:items-end md:gap-5">
      {PODIUM_ORDER.filter((i) => top3[i]).map((i) => {
        const entry = top3[i];
        const isFirst = i === 0;
        return (
          <Link
            key={entry.slug}
            href={`/r/${entry.slug}`}
            className={`group flex flex-col items-center rounded-[2rem] border p-6 shadow-2xl backdrop-blur-md transition-transform hover:-translate-y-1 ${HEIGHT[i]} ${
              isFirst
                ? "border-brand-lime/60 bg-black/80 md:order-2"
                : `border-white/20 bg-black/60 ${i === 1 ? "md:order-1" : "md:order-3"}`
            }`}
          >
            {isFirst && <Crown size={28} className="mb-1 text-brand-lime" strokeWidth={2} />}
            <span
              className={`font-display uppercase tracking-wide ${
                isFirst ? "text-2xl text-brand-lime" : "text-lg text-white/60"
              }`}
            >
              #{entry.rank}
            </span>
            <StampBadge stamp={entry.stamp} className="mt-2" />
            <p className="mt-3 max-w-[10rem] truncate font-mono text-xs font-semibold text-white/80">
              {entry.display_name}
            </p>
            <p className={`mt-1 font-display text-white ${isFirst ? "text-4xl" : "text-3xl"}`}>
              {entry.composite_score}
              <span className="text-sm text-white/40">/100</span>
            </p>
          </Link>
        );
      })}
    </div>
  );
}
