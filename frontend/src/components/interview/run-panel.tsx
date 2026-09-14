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
import type { CodeHarness, DryRunResult, SqlHarness } from "@/lib/interview-api";
import { getRuntime, runCode, runtimeForFormat, runtimeStatus, subscribeToRuntimes } from "@/lib/runners/runtime";
import type { SqlRunResult } from "@/lib/runners/sql.worker";
import type { CaseResult, CodeRunResult } from "@/lib/runners/python.worker";

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

/**
 * "Run" for a CODE round.
 *
 * Python and JavaScript execute in the browser against real test cases.
 * Java and C/C++ have no credible browser runtime, so their Run goes to
 * the server for a READ of the code -- and says so, because telling
 * someone their code passes without running it would be a lie.
 */
export function CodeRunPanel({
  code,
  language,
  harness,
  onDryRun,
  onRunRecorded,
}: {
  code: string;
  language: string;
  harness: CodeHarness;
  onDryRun: (args: { answer: string; language: string }) => Promise<DryRunResult>;
  /** Run history goes to the interviewer as context. Deliberately NOT a
   *  score deduction: penalising failed runs would teach candidates to
   *  stop testing, which is the opposite of what we want. */
  onRunRecorded?: (failed: boolean) => void;
}) {
  const [cases, setCases] = useState<CaseResult[] | null>(null);
  const [failure, setFailure] = useState<{ message: string; phase?: string } | null>(null);
  const [dry, setDry] = useState<DryRunResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(() => runtimeStatus("python"));

  useEffect(() => subscribeToRuntimes(() => setStatus(runtimeStatus("python"))), []);

  const kind = runtimeForFormat("CODE", language);
  const entry = harness.entry[language];

  const run = useCallback(async () => {
    if (!code.trim()) return;
    setBusy(true);
    setCases(null);
    setFailure(null);
    setDry(null);
    try {
      if (!kind || !entry) {
        // Java / C++: assessed, not executed.
        const assessment = await onDryRun({ answer: code, language });
        setDry(assessment);
        onRunRecorded?.(!assessment.looks_correct);
        return;
      }
      // Only the VISIBLE cases here. Hidden ones run at submit time and
      // their outcome is never shown, so tweaking until green buys nothing.
      const visible = harness.cases.filter((c) => !c.hidden);
      const result = (await runCode(kind, {
        kind: harness.kind,
        entry,
        code,
        cases: visible,
      })) as CodeRunResult;

      if (!result.ok) {
        setFailure({ message: result.error ?? "Something went wrong.", phase: result.phase });
        onRunRecorded?.(true);
      } else {
        const results = result.results ?? [];
        setCases(results);
        onRunRecorded?.(results.some((r) => !r.passed));
      }
    } catch (e) {
      setFailure({ message: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }, [code, language, kind, entry, harness, onDryRun, onRunRecorded]);

  const passed = cases?.filter((c) => c.passed).length ?? 0;
  const runnable = kind !== null;

  return (
    <div className="flex shrink-0 flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => void run()}
          disabled={busy || !code.trim()}
          className="flex items-center gap-1.5 rounded-full border-2 border-black bg-white px-4 py-1.5 font-mono text-[11px] font-black uppercase tracking-wide text-black shadow-[3px_3px_0_#000] transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[2px_2px_0_#000] disabled:opacity-40 disabled:shadow-none"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} strokeWidth={3} />}
          {busy ? (runnable ? "Running" : "Checking") : runnable ? "Run tests" : "Check my code"}
        </button>

        {/* Never imply Java/C++ were executed. */}
        {!runnable ? (
          <span className="font-mono text-[10px] text-white/45">
            {LANGUAGE_NOTE[language] ?? "read by the interviewer, not executed"}
          </span>
        ) : status === "warming" && !busy ? (
          <span className="font-mono text-[10px] text-white/45">loading Python in the background…</span>
        ) : null}

        {cases ? (
          <span
            className={`font-mono text-[10px] font-bold ${passed === cases.length ? "text-brand-lime" : "text-amber-300"}`}
          >
            {passed}/{cases.length} tests passing
          </span>
        ) : null}
      </div>

      <AnimatePresence initial={false}>
        {cases || failure || dry ? (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            {failure ? (
              <div className="flex items-start gap-2 rounded-xl border-2 border-red-500/60 bg-red-500/10 px-3 py-2">
                <AlertTriangle size={13} className="mt-0.5 shrink-0 text-red-400" />
                <div className="min-w-0">
                  <p className="font-mono text-[11px] font-bold text-red-300">
                    {failure.phase === "define" ? "Your code didn't load." : "Couldn't run it."}
                  </p>
                  <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-[10.5px] leading-snug text-red-200/80">
                    {failure.message}
                  </pre>
                </div>
              </div>
            ) : dry ? (
              <div className="rounded-xl border-2 border-sky-500/50 bg-sky-500/10 px-3 py-2">
                <p className="mb-1 font-mono text-[11px] font-bold text-sky-300">
                  Read, not run — {dry.looks_correct ? "looks about right" : "there are problems"}
                </p>
                <p className="font-mono text-[10.5px] text-sky-100/70">{dry.summary}</p>
                {dry.problems.length ? (
                  <ul className="mt-1.5 flex flex-col gap-0.5">
                    {dry.problems.map((problem, i) => (
                      <li key={i} className="font-mono text-[10.5px] text-sky-100/70">
                        &bull; {problem}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : (
              <div className="max-h-40 overflow-auto rounded-xl border-2 border-black/30 bg-black/30 px-3 py-2">
                {cases?.map((result, i) => (
                  <div key={i} className="border-b border-white/5 py-1 last:border-0">
                    <p className="flex items-center gap-1.5 font-mono text-[11px]">
                      {result.passed ? (
                        <Check size={11} strokeWidth={3} className="shrink-0 text-brand-lime" />
                      ) : (
                        <X size={11} strokeWidth={3} className="shrink-0 text-amber-400" />
                      )}
                      <span className={result.passed ? "text-white/55" : "text-white/85"}>{result.name}</span>
                    </p>
                    {!result.passed ? (
                      <div className="mt-0.5 pl-4">
                        {result.error ? (
                          <pre className="whitespace-pre-wrap font-mono text-[10px] text-red-300/80">{result.error}</pre>
                        ) : (
                          <pre className="whitespace-pre-wrap break-words font-mono text-[10px] leading-snug text-white/50">
                            got {result.got}
                            {"\n"}want {result.expected}
                          </pre>
                        )}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

const LANGUAGE_NOTE: Record<string, string> = {
  java: "Java can't run in a browser — this is a read of your code",
  cpp: "C/C++ can't run in a browser — this is a read of your code",
};
