import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { StampBadge } from "@/components/leaderboard/stamp-badge";
import { RadarChart } from "@/components/result/radar-chart";
import { relativeTime } from "@/lib/relative-time";
import type { RoastAnalysis } from "@/lib/api";

// One shared blue card, latest-roast summary and its subscore radar side
// by side -- both are "about the same roast," so splitting them into two
// separate cards would just duplicate the score/stamp context between
// them for no reason.
export function LatestRoastAndRadar({ roast }: { roast: RoastAnalysis }) {
  return (
    <div className="relative overflow-hidden rounded-2xl border-[3px] border-black bg-brand-blue-deep px-6 py-6 shadow-[5px_5px_0_#000] md:px-8">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff12_1px,transparent_1px),linear-gradient(to_bottom,#ffffff12_1px,transparent_1px)] bg-[size:3rem_3rem]" />

      <div className="relative z-10 grid grid-cols-1 items-center gap-8 lg:grid-cols-2">
        <div className="flex h-full flex-col lg:border-r lg:border-white/15 lg:pr-8">
          <div className="mb-4 flex items-center justify-between">
            <span className="font-mono text-[10px] font-bold uppercase tracking-wide text-white/50">Latest roast</span>
            <span className="font-mono text-[10px] font-semibold text-white/40">{relativeTime(roast.created_at)}</span>
          </div>

          <div className="mb-4 flex items-center gap-4">
            <span className="font-display leading-none text-white" style={{ fontSize: "3.2rem" }}>
              {roast.composite_score}
            </span>
            <StampBadge stamp={roast.stamp} size="lg" />
          </div>

          <p className="mb-auto font-display text-lg leading-snug text-white">&ldquo;{roast.verdict}&rdquo;</p>

          <Link
            href={`/r/${roast.slug}`}
            className="mt-5 flex items-center justify-center gap-2 rounded-full border-2 border-black bg-brand-lime px-5 py-2.5 font-display text-xs uppercase tracking-wide text-black shadow-[3px_3px_0_#000] transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[1px_1px_0_#000]"
          >
            View full roast
            <ArrowRight size={14} strokeWidth={2.5} />
          </Link>
        </div>

        <RadarChart subscores={roast.subscores} variant="dark" title="Subscore radar" size={280} />
      </div>
    </div>
  );
}
