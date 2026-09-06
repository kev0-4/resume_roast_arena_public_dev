// Same lime-outline treatment as the roast card itself and its other
// frontend appearances (score-banner.tsx, the landing page's example
// cards) -- no per-tier color scheme exists anywhere else in this build,
// so this doesn't invent one.
const STAMP_COPY: Record<string, string> = {
  ROASTED: "Roasted",
  SOLID: "Solid",
  MID: "Mid",
};

export function StampBadge({
  stamp,
  variant = "dark",
  className = "",
}: {
  stamp: string | null;
  // "dark" = lime-on-transparent, for the dark hero/podium cards.
  // "light" = blue-on-white, for rows sitting on the white list panel.
  variant?: "dark" | "light";
  className?: string;
}) {
  if (!stamp) return null;
  const colors = variant === "dark" ? "border-brand-lime text-brand-lime" : "border-brand-blue text-brand-blue";
  return (
    <span className={`rounded-md border-2 px-2 py-0.5 font-display text-[10px] uppercase tracking-wide ${colors} ${className}`}>
      {STAMP_COPY[stamp] ?? stamp}
    </span>
  );
}
