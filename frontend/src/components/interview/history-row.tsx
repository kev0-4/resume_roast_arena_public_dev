"use client";

// One row of a candidate's own interview history. Deliberately NOT a
// <Link> to a result page the way dashboard/history-row.tsx links a
// finished roast to /r/{slug} -- no such page exists for a past
// interview (the live room page only knows how to run a NEW session; it
// has no state to re-show a finished one). GET /interview/{id} already
// returns everything a result view would need (score, strengths,
// weaknesses, next_steps), so a completed row expands in place instead
// of linking somewhere that would just say "this room has closed."

import { useState } from "react";
import { AlertCircle, ChevronDown, Loader2 } from "lucide-react";
import { relativeTime } from "@/lib/relative-time";
import { getInterview, type InterviewDetail, type MyInterviewEntry } from "@/lib/interview-api";
import { useAuth } from "@/lib/auth-context";

function statusBucket(status: string): "done" | "failed" | "processing" {
  if (status === "COMPLETED") return "done";
  if (status === "FAILED" || status === "ABANDONED") return "failed";
  return "processing";
}

export function InterviewHistoryRow({ entry }: { entry: MyInterviewEntry }) {
  const { getIdToken } = useAuth();
  const bucket = statusBucket(entry.status);
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<InterviewDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const canExpand = bucket === "done";

  const toggle = async () => {
    if (!canExpand) return;
    if (expanded) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    if (detail) return;
    setLoadingDetail(true);
    try {
      const idToken = await getIdToken();
      if (!idToken) return;
      setDetail(await getInterview(entry.id, idToken));
    } catch {
      // Leave detail null -- the expanded panel below shows a fallback.
    } finally {
      setLoadingDetail(false);
    }
  };

  return (
    <div className="border-b border-black/8 last:border-0">
      <button
        onClick={toggle}
        disabled={!canExpand}
        className={`group flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors md:gap-4 ${
          canExpand ? "hover:bg-black/[0.02]" : "cursor-default"
        }`}
      >
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[11px] font-semibold text-black/40">{relativeTime(entry.created_at)}</p>
          <p className="mt-0.5 truncate font-mono text-xs text-black/60">
            {entry.vertical ? `${entry.vertical} · ` : ""}
            {entry.job_description}
          </p>
        </div>

        {bucket === "done" && entry.score !== null && (
          <span className="flex-shrink-0 font-display text-lg tabular-nums text-black">
            {entry.score}
            <span className="text-xs text-black/40">/10</span>
          </span>
        )}

        {bucket === "processing" && (
          <span className="flex flex-shrink-0 items-center gap-1.5 rounded-full bg-black/5 px-3 py-1 font-mono text-xs font-semibold text-black/60">
            <Loader2 size={12} className="animate-spin" />
            In progress
          </span>
        )}

        {bucket === "failed" && (
          <span className="flex flex-shrink-0 items-center gap-1.5 rounded-full bg-tier-roasted/10 px-3 py-1 font-mono text-xs font-semibold text-tier-roasted">
            <AlertCircle size={12} />
            {entry.status === "ABANDONED" ? "Abandoned" : "Failed"}
          </span>
        )}

        {canExpand && (
          <ChevronDown
            size={16}
            className={`flex-shrink-0 text-black/20 transition-transform ${expanded ? "rotate-180" : ""}`}
          />
        )}
      </button>

      {expanded && (
        <div className="border-t border-black/8 bg-black/[0.015] px-4 py-4 md:px-6">
          {loadingDetail ? (
            <div className="space-y-2">
              <div className="h-3 w-3/4 animate-pulse rounded bg-black/10" />
              <div className="h-3 w-1/2 animate-pulse rounded bg-black/10" />
            </div>
          ) : !detail ? (
            <p className="font-mono text-xs text-black/50">Could not load this interview&apos;s feedback.</p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {detail.strengths && detail.strengths.length > 0 && (
                <div>
                  <p className="mb-1.5 font-mono text-[10px] font-black uppercase tracking-wider text-black/40">
                    Worked
                  </p>
                  <ul className="space-y-1">
                    {detail.strengths.map((s, i) => (
                      <li key={i} className="font-mono text-xs leading-relaxed text-black/70">
                        + {s}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {detail.weaknesses && detail.weaknesses.length > 0 && (
                <div>
                  <p className="mb-1.5 font-mono text-[10px] font-black uppercase tracking-wider text-black/40">
                    Didn&apos;t
                  </p>
                  <ul className="space-y-1">
                    {detail.weaknesses.map((w, i) => (
                      <li key={i} className="font-mono text-xs leading-relaxed text-black/70">
                        − {w}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {detail.next_steps && detail.next_steps.length > 0 && (
                <div className="md:col-span-2">
                  <p className="mb-1.5 font-mono text-[10px] font-black uppercase tracking-wider text-black/40">
                    Next time
                  </p>
                  <ul className="space-y-1">
                    {detail.next_steps.map((n, i) => (
                      <li key={i} className="font-mono text-xs leading-relaxed text-black/70">
                        → {n}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
