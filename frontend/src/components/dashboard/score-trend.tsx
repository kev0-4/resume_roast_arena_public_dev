import { TrendingUp } from "lucide-react";

// Plain SVG line chart, no library, same reasoning as radar-chart.tsx.
// `scores` must already be chronological (oldest first) -- the caller
// (dashboard page) is responsible for that, this component just draws.
export function ScoreTrend({ scores }: { scores: number[] }) {
  if (scores.length < 2) {
    return (
      <div className="flex flex-col items-center rounded-2xl border-[3px] border-black bg-white px-5 py-10 text-center shadow-[5px_5px_0_#000]">
        <TrendingUp size={22} className="mb-2 text-black/20" />
        <p className="font-mono text-sm font-semibold text-black/45">Roast a couple more resumes to see your trend.</p>
      </div>
    );
  }

  const w = 720;
  const h = 160;
  const pad = 20;
  const max = Math.max(...scores, 100);
  const min = Math.min(...scores, 0);
  const range = Math.max(max - min, 1);
  const stepX = (w - pad * 2) / (scores.length - 1);
  const points = scores.map((s, i) => ({ x: pad + i * stepX, y: pad + (h - pad * 2) * (1 - (s - min) / range) }));
  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${h - pad} L ${points[0].x} ${h - pad} Z`;

  return (
    <div className="rounded-2xl border-[3px] border-black bg-white px-5 py-5 shadow-[5px_5px_0_#000]">
      <div className="mb-3 flex items-center gap-2">
        <TrendingUp size={16} className="text-brand-blue" strokeWidth={2.3} />
        <h3 className="font-display text-sm uppercase tracking-tight text-black">Score trend</h3>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-auto w-full" preserveAspectRatio="none">
        <defs>
          <linearGradient id="score-trend-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--brand-lime)" stopOpacity={0.55} />
            <stop offset="100%" stopColor="var(--brand-lime)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <path d={areaPath} fill="url(#score-trend-fill)" stroke="none" />
        <path d={linePath} fill="none" stroke="var(--brand-blue)" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={4} fill="var(--brand-lime)" stroke="black" strokeWidth={1.5} />
        ))}
      </svg>
    </div>
  );
}
