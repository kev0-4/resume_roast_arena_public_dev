// Plain-SVG radar/spider chart for the per-category subscores
// (backend/src/routes/public.py:_compute_subscores) -- real deductions
// from this session's own rule-engine issues, not invented numbers, same
// grounding standard as the highlights feature. No charting library: the
// trig here is the same regardless of library, and pulling one in for a
// single hand-sized chart isn't worth it.
//
// Two variants: "light" (white result-page panel -- black text/grid) and
// "dark" (the dashboard's blue hero card -- white text, faint white grid,
// white points so they don't vanish against the same blue the polygon's
// point-fill would otherwise blend into).
const VARIANT_COLORS = {
  light: { grid: "rgba(0,0,0,0.1)", label: "black", pointFill: "var(--brand-blue)", pointStroke: "#000000" },
  dark: { grid: "rgba(255,255,255,0.18)", label: "white", pointFill: "#ffffff", pointStroke: "var(--brand-blue)" },
};
const FILL_COLOR = "var(--brand-lime)";
const STROKE_COLOR = "#000000";
const LEVELS = 4;
const MAX_VALUE = 100;

function polarToCartesian(angle: number, radius: number) {
  return { x: radius * Math.sin(angle), y: -radius * Math.cos(angle) };
}

export function RadarChart({
  subscores,
  variant = "light",
  title = "Where you actually stand",
  size = 340,
}: {
  subscores: Record<string, number>;
  variant?: "light" | "dark";
  title?: string | null;
  size?: number;
}) {
  const data = Object.entries(subscores);
  if (data.length < 3) return null; // a radar chart needs at least a triangle

  const colors = VARIANT_COLORS[variant];
  const margin = size < 300 ? 56 : 72;
  const radius = (size - margin * 2) / 2;
  const step = (Math.PI * 2) / data.length;

  const scaledRadius = (value: number) => (value / MAX_VALUE) * radius;
  const axisPoints = data.map((_, i) => polarToCartesian(i * step, radius));
  const dataPoints = data.map(([, value], i) => polarToCartesian(i * step, scaledRadius(value)));
  const polygonStr = dataPoints.map((p) => `${p.x},${p.y}`).join(" ");
  const labelPoints = data.map((_, i) => polarToCartesian(i * step, radius + 20));

  return (
    <div className="w-full">
      {title && (
        <h3
          className={`mb-4 font-display text-lg uppercase tracking-tight md:text-xl ${
            variant === "dark" ? "text-white/70" : "text-black"
          }`}
        >
          {title}
        </h3>
      )}
      <div className="flex justify-center">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="max-w-full">
          <g transform={`translate(${size / 2}, ${size / 2})`}>
            {[...Array(LEVELS)].map((_, ringIdx) => {
              const ringRadius = ((ringIdx + 1) * radius) / LEVELS;
              const ringPoints = data.map((_, i) => polarToCartesian(i * step, ringRadius));
              return (
                <polygon
                  key={`ring-${ringIdx}`}
                  points={ringPoints.map((p) => `${p.x},${p.y}`).join(" ")}
                  fill="none"
                  stroke={colors.grid}
                  strokeWidth={1}
                />
              );
            })}

            {axisPoints.map((p, i) => (
              <line key={`spoke-${i}`} x1={0} y1={0} x2={p.x} y2={p.y} stroke={colors.grid} strokeWidth={1} />
            ))}

            <polygon
              points={polygonStr}
              fill={FILL_COLOR}
              fillOpacity={0.55}
              stroke={STROKE_COLOR}
              strokeWidth={2.5}
              strokeLinejoin="round"
            />

            {dataPoints.map((p, i) => (
              <circle key={`point-${i}`} cx={p.x} cy={p.y} r={4} fill={colors.pointFill} stroke={colors.pointStroke} strokeWidth={1.5} />
            ))}

            {labelPoints.map((p, i) => {
              const [label, value] = data[i];
              const anchor = Math.abs(p.x) < 4 ? "middle" : p.x > 0 ? "start" : "end";
              return (
                <g key={`label-${i}`} transform={`translate(${p.x}, ${p.y})`}>
                  <text
                    textAnchor={anchor}
                    dominantBaseline="middle"
                    className="font-display"
                    fontSize={size < 300 ? 9 : 11}
                    fill={colors.label}
                    style={{ textTransform: "uppercase", letterSpacing: "0.02em" }}
                  >
                    {label}
                  </text>
                  <text
                    textAnchor={anchor}
                    dominantBaseline="middle"
                    y={13}
                    className="font-mono"
                    fontSize={size < 300 ? 8 : 10}
                    fontWeight={700}
                    fill={variant === "dark" ? "var(--brand-lime)" : "var(--brand-blue)"}
                  >
                    {value}/100
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    </div>
  );
}
