// No real per-user avatar image exists for leaderboard entries (display
// names are anonymous-by-default fun names, not real accounts with
// photos) -- a deterministic initial + hue keeps rows visually distinct
// from each other without needing one.
function hueFromName(name: string): number {
  let sum = 0;
  for (const ch of name) sum += ch.charCodeAt(0);
  return sum % 360;
}

export function Avatar({ name, size = 36 }: { name: string; size?: number }) {
  const initial = (name || "?").trim().charAt(0).toUpperCase();
  const hue = hueFromName(name || "x");
  return (
    <div
      className="flex flex-shrink-0 items-center justify-center rounded-full border-2 border-black font-display text-white"
      style={{ width: size, height: size, background: `hsl(${hue}, 65%, 45%)`, fontSize: size * 0.42 }}
    >
      {initial}
    </div>
  );
}
