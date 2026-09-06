"use client";

import { motion } from "framer-motion";
import type { ScoreSummary } from "@/lib/api";

const ROWS: { key: keyof ScoreSummary; label: string; color: string }[] = [
  { key: "critical_issues", label: "Critical", color: "#EF4444" },
  { key: "high_issues", label: "High", color: "#F97316" },
  { key: "medium_issues", label: "Medium", color: "#EAB308" },
  { key: "low_issues", label: "Low", color: "#38BDF8" },
  { key: "total_strengths", label: "Strengths", color: "#CCFF00" },
];

export function SeverityChart({ summary }: { summary: ScoreSummary }) {
  const max = Math.max(1, ...ROWS.map((r) => summary[r.key]));

  return (
    <div className="w-full">
      <h3 className="mb-4 font-display text-lg uppercase tracking-tight text-black md:text-xl">
        What the rule engine found
      </h3>
      <div className="flex flex-col gap-3">
        {ROWS.map((row) => {
          const count = summary[row.key];
          const widthPct = (count / max) * 100;
          return (
            <div key={row.key} className="flex items-center gap-3">
              <span className="w-20 flex-shrink-0 font-mono text-xs font-semibold uppercase text-black/60">
                {row.label}
              </span>
              <div className="h-6 flex-1 overflow-hidden rounded-full bg-black/5">
                <motion.div
                  className="h-full rounded-full"
                  style={{ backgroundColor: row.color }}
                  initial={{ width: 0 }}
                  whileInView={{ width: `${widthPct}%` }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.6, ease: "easeOut" }}
                />
              </div>
              <span className="w-6 flex-shrink-0 text-right font-mono text-sm font-bold text-black">
                {count}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
