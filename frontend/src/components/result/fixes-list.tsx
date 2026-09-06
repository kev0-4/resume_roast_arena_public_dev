import { CheckCircle2 } from "lucide-react";

export function FixesList({ fixes }: { fixes: string[] }) {
  if (fixes.length === 0) return null;

  return (
    <div>
      <h3 className="mb-4 font-display text-lg uppercase tracking-tight text-black md:text-xl">
        Fix these
      </h3>
      <div className="flex flex-col gap-2">
        {fixes.map((fix, i) => (
          <div key={i} className="flex items-start gap-3 rounded-2xl border border-black/5 bg-paper p-4">
            <CheckCircle2 size={20} className="mt-0.5 flex-shrink-0 text-brand-blue" strokeWidth={2} />
            <p className="font-mono text-sm text-black/80 md:text-base">{fix}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
