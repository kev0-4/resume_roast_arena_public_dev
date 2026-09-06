import { Quote } from "lucide-react";
import type { Highlight } from "@/lib/api";

// Every quote here is a real, verified-verbatim excerpt from the actual
// resume (grounded server-side, see workers/llm/pipeline/validator.py) --
// not the LLM paraphrasing or inventing. Worth that context existing
// somewhere near this component even though it's not shown in the UI copy.
export function HighlightsList({ highlights }: { highlights: Highlight[] }) {
  if (highlights.length === 0) return null;

  return (
    <div>
      <h3 className="mb-4 font-display text-lg uppercase tracking-tight text-black md:text-xl">
        Receipts
      </h3>
      <div className="flex flex-col gap-3">
        {highlights.map((h, i) => (
          <div
            key={i}
            className="relative rounded-2xl border border-black/5 bg-brand-blue p-5 pl-12 text-white shadow-sm"
          >
            <Quote size={20} className="absolute left-4 top-5 text-brand-lime" strokeWidth={2.5} />
            <p className="font-display text-base leading-snug md:text-lg">&ldquo;{h.quote}&rdquo;</p>
            <p className="mt-2 font-mono text-xs text-white/70 md:text-sm">{h.comment}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
