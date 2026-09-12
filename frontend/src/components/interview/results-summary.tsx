import Link from "next/link";
import { ArrowRight, CheckCircle2, TrendingUp, XCircle } from "lucide-react";

// 1-10 scale -- deliberately not styled like the resume roast's 0-100
// SOLID/MID/ROASTED stamp system (a different metric, see
// components/interview-leaderboard/'s own duplication of the leaderboard
// components for the same reasoning).
export function ResultsSummary({
  score,
  strengths,
  weaknesses,
  nextSteps,
}: {
  score: number;
  strengths: string[];
  weaknesses: string[];
  nextSteps: string[];
}) {
  return (
    <div className="w-full rounded-[1.75rem] border-[3px] border-black bg-white p-6 shadow-[6px_6px_0_#000] md:p-8">
      <div className="flex flex-col items-center border-b border-black/10 pb-6 text-center">
        <p className="font-mono text-xs font-black uppercase tracking-wide text-black/40">Interview score</p>
        <p className="mt-1 font-display text-6xl text-black">
          {score}
          <span className="text-2xl text-black/30">/10</span>
        </p>
      </div>

      <div className="mt-6 flex flex-col gap-6">
        {strengths.length > 0 && (
          <div>
            <p className="mb-2 flex items-center gap-1.5 font-mono text-xs font-black uppercase tracking-wide text-black/50">
              <CheckCircle2 size={14} className="text-brand-lime" />
              What worked
            </p>
            <ul className="flex flex-col gap-1.5">
              {strengths.map((s, i) => (
                <li key={i} className="font-mono text-sm text-black/80">
                  {s}
                </li>
              ))}
            </ul>
          </div>
        )}

        {weaknesses.length > 0 && (
          <div>
            <p className="mb-2 flex items-center gap-1.5 font-mono text-xs font-black uppercase tracking-wide text-black/50">
              <XCircle size={14} className="text-red-500" />
              What didn&apos;t
            </p>
            <ul className="flex flex-col gap-1.5">
              {weaknesses.map((w, i) => (
                <li key={i} className="font-mono text-sm text-black/80">
                  {w}
                </li>
              ))}
            </ul>
          </div>
        )}

        {nextSteps.length > 0 && (
          <div>
            <p className="mb-2 flex items-center gap-1.5 font-mono text-xs font-black uppercase tracking-wide text-black/50">
              <TrendingUp size={14} className="text-brand-blue" />
              Fix these
            </p>
            <ul className="flex flex-col gap-1.5">
              {nextSteps.map((n, i) => (
                <li key={i} className="font-mono text-sm text-black/80">
                  {n}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="mt-8 flex flex-col items-center gap-3 border-t border-black/10 pt-6">
        <Link
          href="/interview-leaderboard"
          className="flex items-center gap-2 rounded-full bg-brand-blue px-8 py-4 font-display text-sm uppercase tracking-wide text-white shadow-[4px_4px_0_#000] transition-all hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0_#000] md:text-base"
        >
          See the leaderboard
          <ArrowRight size={18} strokeWidth={2.5} />
        </Link>
      </div>
    </div>
  );
}
