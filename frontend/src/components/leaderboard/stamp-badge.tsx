const STAMP_COPY: Record<string, string> = {
  ROASTED: "Roasted",
  SOLID: "Solid",
  MID: "Mid",
};

// Solid black-bordered pill per tier, filled with the tier's own color --
// previously every stamp badge was a uniform lime outline regardless of
// tier (score-banner.tsx, the landing page's example cards still are);
// this is a deliberate, more legible upgrade for the leaderboard
// specifically, where multiple tiers sit side by side and need to read
// apart at a glance. ROASTED gets white text (its red is too dark for
// black text to sit comfortably on); the other two keep black text.
const TIER_STYLE: Record<string, string> = {
  SOLID: "bg-brand-lime text-black",
  MID: "bg-tier-mid text-black",
  ROASTED: "bg-tier-roasted text-white",
};

export function StampBadge({
  stamp,
  size = "sm",
  className = "",
}: {
  stamp: string | null;
  size?: "sm" | "lg";
  className?: string;
}) {
  if (!stamp) return null;
  const colors = TIER_STYLE[stamp] ?? "bg-brand-lime text-black";
  const sizing = size === "lg" ? "px-3 py-1.5 text-xs" : "px-2.5 py-1 text-[10px]";
  return (
    <span className={`inline-flex items-center rounded-lg border-2 border-black font-display uppercase tracking-wide ${sizing} ${colors} ${className}`}>
      {STAMP_COPY[stamp] ?? stamp}
    </span>
  );
}
