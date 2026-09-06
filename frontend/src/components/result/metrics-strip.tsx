type MetricsDict = Record<string, number | string | null>;

// Curated subset -- the real metrics dict has more fields (character_count,
// experience_date_count, metric_density, etc.) than are worth surfacing on
// a result page; these four are the ones a person actually cares about.
function buildStats(metrics: MetricsDict) {
  const wordCount = metrics.word_count;
  const avgSentence = metrics.avg_sentence_length;
  const lexicalDiversity = metrics.lexical_diversity;
  const experienceBlocks = metrics.experience_block_count;

  return [
    { label: "Word count", value: typeof wordCount === "number" ? wordCount : "—" },
    {
      label: "Avg sentence length",
      value: typeof avgSentence === "number" ? avgSentence.toFixed(1) : "—",
    },
    {
      label: "Lexical diversity",
      value: typeof lexicalDiversity === "number" ? `${Math.round(lexicalDiversity * 100)}%` : "—",
    },
    { label: "Experience blocks", value: typeof experienceBlocks === "number" ? experienceBlocks : "—" },
  ];
}

export function MetricsStrip({ metrics }: { metrics: MetricsDict }) {
  const stats = buildStats(metrics);
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {stats.map((stat) => (
        <div key={stat.label} className="rounded-2xl border border-black/5 bg-paper p-4 text-center">
          <p className="font-display text-2xl text-black md:text-3xl">{stat.value}</p>
          <p className="mt-1 font-mono text-[10px] font-semibold uppercase tracking-wide text-smoke">
            {stat.label}
          </p>
        </div>
      ))}
    </div>
  );
}
