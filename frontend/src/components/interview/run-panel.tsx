"use client";

// "Run" for a SQL round, plus the result it produces.
//
// This is a SELF-CHECK, not grading. The score still comes from the
// server's review of the submission -- running here only spares the
// candidate the indignity of submitting an answer they were never able to
// try, which is the single most unrealistic thing about a read-only
// editor.

import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Check, Loader2, Play, X } from "lucide-react";
import type { SqlHarness } from "@/lib/interview-api";
import { getRuntime, runtimeStatus, subscribeToRuntimes } from "@/lib/runners/runtime";
import type { SqlRunResult } from "@/lib/runners/sql.worker";

type Outcome =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "passed"; ms: number }
  | { kind: "failed"; rows: unknown[][]; expected: unknown[][]; ms: number }
  | { kind: "error"; message: string; phase?: string };

/** Loose compare: Postgres hands back numbers, dates and booleans in its
 *  own shapes, and a candidate should not fail on `1` vs `"1"`. */
function sameRows(a: unknown[][], b: unknown[][]): boolean {
  if (a.length !== b.length) return false;
  const norm = (v: unknown) =>
    v === null || v === undefined
      ? ""
      : v instanceof Date
        ? v.toISOString().slice(0, 19).replace("T", " ")
        : String(v).trim();
  return a.every((row, i) => row.length === b[i].length && row.every((cell, j) => norm(cell) === norm(b[i][j])));
}

export function SqlRunPanel({ sql, harness }: { sql: string; harness: SqlHarness }) {
  const [outcome, setOutcome] = useState<Outcome>({ kind: "idle" });
  const [status, setStatus] = useState(() => runtimeStatus("sql"));

  useEffect(() => subscribeToRuntimes(() => setStatus(runtimeStatus("sql"))), []);

  const run = useCallback(async () => {
    if (!sql.trim()) return;
    setOutcome({ kind: "running" });
    try {
      const worker = await getRuntime("sql");
      const result = await new Promise<SqlRunResult>((resolve, reject) => {
        const onMessage = (event: MessageEvent<SqlRunResult>) => {
          worker.removeEventListener("message", onMessage);
          resolve(event.data);
        };
        worker.addEventListener("message", onMessage);
        // A runaway query must not hang the round. The worker survives --
        // only this attempt is abandoned.
        const timer = setTimeout(() => {
          worker.removeEventListener("message", onMessage);
          reject(new Error("Query took longer than 15 seconds and was stopped."));
        }, 15000);
        const done = () => clearTimeout(timer);
        worker.addEventListener("message", done, { once: true });

        worker.postMessage({
          setup: harness.setup,
          sql: harness.wrap_candidate_as_view ? `CREATE VIEW candidate_answer AS ${sql.replace(/;\s*$/, "")};` : sql,
          verify: harness.verify,
        });
      });

      if (!result.ok) {
        setOutcome({ kind: "error", message: result.error ?? "Something went wrong.", phase: result.phase });
        return;
      }
      const rows = result.rows ?? [];
      if (sameRows(rows, harness.expected)) setOutcome({ kind: "passed", ms: result.ms ?? 0 });
      else setOutcome({ kind: "failed", rows, expected: harness.expected, ms: result.ms ?? 0 });
    } catch (e) {
      setOutcome({ kind: "error", message: e instanceof Error ? e.message : String(e) });
    }
  }, [sql, harness]);

  const busy = outcome.kind === "running";
  // Warming is background work; the button says so rather than looking broken.
  const label =
    busy ? "Running" : status === "warming" ? "Preparing Postgres" : status === "ready" ? "Run" : "Run";

  return (
    <div className="flex shrink-0 flex-col gap-2">
      <div className="flex items-center gap-2">
        <button
          onClick={() => void run()}
          disabled={busy || !sql.trim()}
          className="flex items-center gap-1.5 rounded-full border-2 border-black bg-white px-4 py-1.5 font-mono text-[11px] font-black uppercase tracking-wide text-black shadow-[3px_3px_0_#000] transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[2px_2px_0_#000] disabled:opacity-40 disabled:shadow-none"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} strokeWidth={3} />}
          {label}
        </button>
        {status === "warming" && !busy ? (
          <span className="font-mono text-[10px] text-white/45">loading Postgres in the background…</span>
        ) : null}
        {outcome.kind === "passed" ? (
          <span className="font-mono text-[10px] font-bold text-brand-lime">
            matches the expected result · {outcome.ms}ms
          </span>
        ) : null}
      </div>

      <AnimatePresence initial={false}>
        {outcome.kind === "failed" || outcome.kind === "error" ? (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            {outcome.kind === "error" ? (
              <div className="flex items-start gap-2 rounded-xl border-2 border-red-500/60 bg-red-500/10 px-3 py-2">
                <AlertTriangle size={13} className="mt-0.5 shrink-0 text-red-400" />
                <div>
                  {/* Never blame the candidate for our own fixtures. */}
                  <p className="font-mono text-[11px] font-bold text-red-300">
                    {outcome.phase === "setup" || outcome.phase === "boot"
                      ? "The test fixtures failed to load — that's on us, not your query."
                      : "Your statement didn't run."}
                  </p>
                  <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-[10.5px] leading-snug text-red-200/80">
                    {outcome.message}
                  </pre>
                </div>
              </div>
            ) : (
              <div className="rounded-xl border-2 border-amber-500/60 bg-amber-500/10 px-3 py-2">
                <p className="mb-2 flex items-center gap-1.5 font-mono text-[11px] font-bold text-amber-300">
                  <X size={12} strokeWidth={3} />
                  Ran fine, but the result doesn&apos;t match · {outcome.ms}ms
                </p>
                <div className="grid gap-2 sm:grid-cols-2">
                  <RowTable title="You returned" rows={outcome.rows} />
                  <RowTable title="Expected" rows={outcome.expected} accent />
                </div>
              </div>
            )}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function RowTable({ title, rows, accent }: { title: string; rows: unknown[][]; accent?: boolean }) {
  return (
    <div>
      <p className="mb-1 font-mono text-[9px] font-black uppercase tracking-wider text-white/40">{title}</p>
      <div className="max-h-32 overflow-auto rounded-lg bg-black/30 p-2">
        {rows.length === 0 ? (
          <p className="font-mono text-[10.5px] text-white/35">(no rows)</p>
        ) : (
          rows.map((row, i) => (
            <pre
              key={i}
              className={`whitespace-pre font-mono text-[10.5px] leading-snug ${accent ? "text-brand-lime/90" : "text-white/75"}`}
            >
              {row.map((cell) => (cell === null ? "NULL" : String(cell))).join("  |  ")}
            </pre>
          ))
        )}
      </div>
    </div>
  );
}

export { Check };
