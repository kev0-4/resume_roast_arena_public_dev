// Floating "social proof" cards in the hero -- real anonymous display
// names + scores in the same shape the actual leaderboard/roast card
// produce (see GET /leaderboard, workers/renderer's roast_card.html),
// not invented UI-only content.

export function ExampleRoastCard({
  name,
  score,
  stamp,
}: {
  name: string;
  score: number;
  stamp: string;
}) {
  return (
    <div className="flex aspect-[3/3.3] w-32 flex-col items-center justify-center rounded-[1.5rem] border border-white/20 bg-black/70 p-3 shadow-2xl backdrop-blur-md md:w-52 md:rounded-[2rem] md:p-5">
      <div className="rounded-md border-2 border-brand-lime px-2 py-0.5 font-display text-xs tracking-wide text-brand-lime md:px-3 md:py-1 md:text-sm">
        {stamp}
      </div>
      <div className="mt-3 max-w-full text-center md:mt-4">
        <p className="truncate font-mono text-[10px] font-medium text-white/70 md:text-[11px]">{name}</p>
        <p className="mt-1 font-display text-2xl text-white md:text-3xl">{score}/100</p>
      </div>
    </div>
  );
}
