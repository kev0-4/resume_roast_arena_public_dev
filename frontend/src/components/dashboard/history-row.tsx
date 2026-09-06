import Link from "next/link";
import { AlertCircle, ChevronRight, Loader2 } from "lucide-react";
import { StampBadge } from "@/components/leaderboard/stamp-badge";
import { relativeTime } from "@/lib/relative-time";
import type { MySession } from "@/lib/api";

// The 15 possible SessionStatus values collapse to 3 buckets for display
// -- a history page doesn't need to distinguish EXTRACTED from SCORING,
// only "still going" vs the two terminal states.
function statusBucket(status: MySession["status"]): "done" | "failed" | "processing" {
  if (status === "DONE") return "done";
  if (status === "FAILED") return "failed";
  return "processing";
}

export function HistoryRow({ session }: { session: MySession }) {
  const bucket = statusBucket(session.status);

  const content = (
    <>
      <div className="min-w-0 flex-1">
        <p className="font-mono text-[11px] font-semibold text-black/40">{relativeTime(session.created_at)}</p>
        {bucket === "failed" && session.error_message && (
          <p className="mt-0.5 truncate font-mono text-xs text-black/60">{session.error_message}</p>
        )}
      </div>

      {bucket === "done" && session.composite_score !== null && (
        <>
          <StampBadge stamp={session.stamp} />
          <span className="flex-shrink-0 font-display text-lg tabular-nums text-black">
            {session.composite_score}
            <span className="text-xs text-black/40">/100</span>
          </span>
        </>
      )}

      {bucket === "processing" && (
        <span className="flex flex-shrink-0 items-center gap-1.5 rounded-full bg-black/5 px-3 py-1 font-mono text-xs font-semibold text-black/60">
          <Loader2 size={12} className="animate-spin" />
          Processing
        </span>
      )}

      {bucket === "failed" && (
        <span className="flex flex-shrink-0 items-center gap-1.5 rounded-full bg-tier-roasted/10 px-3 py-1 font-mono text-xs font-semibold text-tier-roasted">
          <AlertCircle size={12} />
          Failed
        </span>
      )}

      <ChevronRight size={16} className="flex-shrink-0 text-black/20 transition-transform group-hover:translate-x-0.5" />
    </>
  );

  const rowClass =
    "group flex items-center gap-3 border-b border-black/8 px-4 py-3.5 transition-colors last:border-0 md:gap-4";

  if (bucket === "done" && session.slug) {
    return (
      <Link href={`/r/${session.slug}`} className={`${rowClass} hover:bg-black/[0.02]`}>
        {content}
      </Link>
    );
  }
  if (bucket === "processing") {
    return (
      <Link href={`/roast/${session.session_id}`} className={`${rowClass} hover:bg-black/[0.02]`}>
        {content}
      </Link>
    );
  }
  return <div className={rowClass}>{content}</div>;
}
