export function RoastPanel({ verdict, roast }: { verdict: string; roast: string }) {
  return (
    <div className="rounded-[2rem] border border-black/5 bg-paper p-6 md:p-8">
      <h3 className="mb-4 font-display text-lg uppercase tracking-tight text-black md:text-xl">
        The roast
      </h3>
      <p className="font-display text-xl leading-tight text-black md:text-2xl">&ldquo;{verdict}&rdquo;</p>
      <div className="mt-4 space-y-3 font-mono text-sm leading-relaxed text-black/70 md:text-base">
        {roast.split("\n").filter(Boolean).map((paragraph, i) => (
          <p key={i}>{paragraph}</p>
        ))}
      </div>
    </div>
  );
}
