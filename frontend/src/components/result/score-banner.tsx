import { AnimatedNumber } from "./animated-number";

const STAMP_COPY: Record<string, string> = {
  ROASTED: "Absolutely roasted.",
  SOLID: "Actually holds up.",
  MID: "Mid. Just mid.",
};

export function ScoreBanner({
  score,
  stamp,
  rank,
  totalRanked,
}: {
  score: number;
  stamp: string;
  rank: number;
  totalRanked: number;
}) {
  const percentile = totalRanked > 0 ? Math.round((1 - (rank - 1) / totalRanked) * 100) : null;

  return (
    <div className="flex flex-col items-center text-center">
      <div className="mb-2 rounded-full border-2 border-brand-lime px-4 py-1 font-display text-sm uppercase tracking-wide text-brand-lime">
        {STAMP_COPY[stamp] ?? stamp}
      </div>
      <div className="flex items-end gap-2">
        <AnimatedNumber value={score} className="font-display text-[clamp(5rem,16vw,10rem)] leading-none text-white" />
        <span className="mb-3 font-mono text-2xl font-bold text-white/50 md:text-4xl">/100</span>
      </div>
      <p className="mt-2 font-mono text-sm text-white/60 md:text-base">
        Rank <span className="font-bold text-brand-lime">#{rank}</span> of {totalRanked}
        {percentile !== null && percentile > 0 && <> — better than {percentile}% of resumes</>}
      </p>
    </div>
  );
}
