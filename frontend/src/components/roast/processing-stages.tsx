"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Clock, FileSearch, Gavel, ListChecks, PenTool, Sparkles, UserX } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { SessionStatus } from "@/lib/api";

// Real backend pipeline order (backend/src/db/sessions.py JobStatusEnum),
// grouped into one visible stage per pair of sub-statuses -- driven by
// the session's actual polled status, not a timer. A status not in this
// list (DONE/FAILED) is handled by the caller, not here.
const STAGE_ORDER: { statuses: SessionStatus[]; label: string; icon: LucideIcon }[] = [
  { statuses: ["UPLOADED", "QUEUED"], label: "Queued up...", icon: Clock },
  { statuses: ["PROCESSING", "EXTRACTED"], label: "Reading your resume...", icon: FileSearch },
  { statuses: ["NORMALIZING", "NORMALIZED"], label: "Making sense of the mess...", icon: ListChecks },
  { statuses: ["ANONYMIZING", "ANONYMIZED"], label: "Redacting your identity...", icon: UserX },
  { statuses: ["SCORING", "SCORED"], label: "Judging your bullet points...", icon: Gavel },
  { statuses: ["ROASTING", "ROASTED"], label: "Writing the roast...", icon: PenTool },
  { statuses: ["RENDERING"], label: "Plating the roast...", icon: Sparkles },
];

const STATUS_TO_STAGE_INDEX: Record<string, number> = STAGE_ORDER.reduce(
  (acc, stage, index) => {
    for (const s of stage.statuses) acc[s] = index;
    return acc;
  },
  {} as Record<string, number>,
);

export function ProcessingStages({ status }: { status: SessionStatus | undefined }) {
  const stageIndex = status ? (STATUS_TO_STAGE_INDEX[status] ?? 0) : 0;
  const stage = STAGE_ORDER[stageIndex];
  const CurrentIcon = stage.icon;
  const progressPct = Math.round(((stageIndex + 1) / STAGE_ORDER.length) * 100);

  return (
    <div className="flex w-full max-w-md flex-col items-center text-center">
      {/* rotating badge -- same motif as the landing hero's spinning CTA
          badge (accents.tsx SpinningRoastBadge), but the center icon
          cross-fades per real pipeline stage instead of being static */}
      <div className="relative mb-8 h-32 w-32 rounded-full border-[3px] border-black/5 bg-brand-lime shadow-xl md:h-36 md:w-36">
        <div className="absolute inset-1 animate-[spin_6s_linear_infinite]">
          <svg viewBox="0 0 100 100" className="h-full w-full">
            <path
              id="processingCirclePath"
              d="M 50, 50 m -36, 0 a 36,36 0 1,1 72,0 a 36,36 0 1,1 -72,0"
              fill="none"
            />
            <text className="font-mono text-[11px] font-bold uppercase tracking-[0.18em]" fill="black">
              <textPath href="#processingCirclePath" startOffset="0%">
                ROASTING IN PROGRESS • ROASTING IN PROGRESS •{" "}
              </textPath>
            </text>
          </svg>
        </div>
        <div className="absolute inset-0 flex items-center justify-center">
          <AnimatePresence mode="wait">
            <motion.div
              key={stageIndex}
              initial={{ opacity: 0, scale: 0.6, rotate: -15 }}
              animate={{ opacity: 1, scale: 1, rotate: 0 }}
              exit={{ opacity: 0, scale: 0.6, rotate: 15 }}
              transition={{ duration: 0.35, ease: "easeOut" }}
            >
              <CurrentIcon size={34} className="text-black" strokeWidth={2} />
            </motion.div>
          </AnimatePresence>
        </div>
      </div>

      <div className="mb-6 flex h-10 items-center justify-center overflow-hidden md:h-12">
        <AnimatePresence mode="wait">
          <motion.p
            key={stageIndex}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="font-display text-xl uppercase tracking-tight text-white md:text-2xl"
          >
            {stage.label}
          </motion.p>
        </AnimatePresence>
      </div>

      <div className="w-full max-w-xs">
        <div className="h-4 w-full overflow-hidden rounded-full border-2 border-black/20 bg-white/15">
          <motion.div
            className="h-full rounded-full bg-brand-lime"
            initial={false}
            animate={{ width: `${progressPct}%` }}
            transition={{ duration: 0.6, ease: "easeOut" }}
          />
        </div>
        <div className="mt-2 flex justify-between">
          <span className="font-mono text-[10px] font-bold uppercase tracking-wide text-white/60">
            Step {stageIndex + 1} of {STAGE_ORDER.length}
          </span>
          <span className="font-mono text-[10px] font-black text-brand-lime">{progressPct}%</span>
        </div>
      </div>

      <div className="mt-6 flex items-center gap-2">
        {STAGE_ORDER.map((s, i) => (
          <span
            key={s.label}
            className={[
              "h-2.5 w-2.5 rounded-full transition-colors duration-300",
              i < stageIndex ? "bg-brand-lime" : i === stageIndex ? "animate-pulse bg-white" : "bg-white/20",
            ].join(" ")}
          />
        ))}
      </div>
    </div>
  );
}
