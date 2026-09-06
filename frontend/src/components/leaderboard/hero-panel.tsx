import { Podium } from "./podium";
import type { LeaderboardEntry } from "@/lib/api";

// Tightly sized around its own content (title + tagline + podium) --
// previously this content lived in a full-viewport-height flex column
// with a separate white section stacked below it, which produced a lot
// of dead blue space whenever the podium itself was short. A single
// bordered card fixes both problems at once: it only ever takes the
// height its content needs, and it reads as one deliberate block sitting
// on the page's single background color instead of two competing
// full-width color zones.
export function HeroPanel({ entries, total }: { entries: LeaderboardEntry[]; total: number | null }) {
  return (
    <div className="relative w-full overflow-hidden rounded-[1.75rem] border-[3px] border-black bg-brand-blue-deep px-6 pb-6 pt-8 shadow-[6px_6px_0_#000] md:pt-9">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff12_1px,transparent_1px),linear-gradient(to_bottom,#ffffff12_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      <div className="relative z-10 mb-6 flex flex-col items-center text-center">
        <h1 className="font-display text-[clamp(1.8rem,5vw,2.6rem)] uppercase leading-[0.95] tracking-tighter text-white">
          The <span className="text-brand-lime">leaderboard</span>
        </h1>
        <p className="mt-1.5 max-w-sm font-mono text-xs text-white/60 md:text-sm">
          Every roast that made the cut, ranked by score.
          {total !== null && <> {total} resumes roasted and counting.</>}
        </p>
      </div>

      <div className="relative z-10">
        <Podium entries={entries} />
      </div>
    </div>
  );
}
