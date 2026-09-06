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
    <div className="flex aspect-[3/3.3] w-40 flex-col items-center justify-center rounded-[2rem] border border-white/20 bg-black/70 p-5 shadow-2xl backdrop-blur-md md:w-52">
      <div className="rounded-md border-2 border-brand-lime px-3 py-1 font-display text-sm tracking-wide text-brand-lime">
        {stamp}
      </div>
      <div className="mt-4 text-center">
        <p className="font-mono text-[11px] font-medium text-white/70">{name}</p>
        <p className="mt-1 font-display text-3xl text-white">{score}/100</p>
      </div>
    </div>
  );
}
