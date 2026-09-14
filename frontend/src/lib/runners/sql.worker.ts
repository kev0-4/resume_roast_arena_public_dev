// Runs the candidate's SQL against a real Postgres, in a Web Worker.
//
// A worker rather than the main thread for two reasons, and neither is
// security: PGlite's boot is ~5MB of WASM plus an init that would jank the
// main thread, and the main thread is where the live audio socket's
// messages and base64 encoding happen. Nothing about a coding round is
// allowed to make the interviewer stutter.
//
// PGlite is real Postgres compiled to WASM, chosen over SQLite because the
// questions are written in Postgres -- MERGE and the window functions in
// the sessionisation question are not portable to SQLite.

import { PGlite } from "@electric-sql/pglite";

export interface SqlRunRequest {
  /** DDL + fixture rows. Run before the candidate's statement. */
  setup: string[];
  /** Whatever the candidate wrote. */
  sql: string;
  /** Read-back query, run after theirs, whose rows are compared. */
  verify: string;
}

export interface SqlRunResult {
  ok: boolean;
  /** Rows from `verify`, as arrays in column order. */
  rows?: unknown[][];
  columns?: string[];
  error?: string;
  /** Which phase failed, so the candidate is never blamed for our fixtures. */
  phase?: "boot" | "setup" | "candidate" | "verify";
  ms?: number;
}

let dbPromise: Promise<PGlite> | null = null;

/** One database per worker, booted once and reused across runs. */
function getDb(): Promise<PGlite> {
  if (!dbPromise) dbPromise = PGlite.create();
  return dbPromise;
}

self.onmessage = async (event: MessageEvent<SqlRunRequest | { warmup: true }>) => {
  const started = performance.now();

  // A warm-up message boots Postgres without running anything, so the
  // download and init happen during the conversation round instead of
  // while the candidate is staring at an editor.
  if ("warmup" in event.data) {
    try {
      await getDb();
      self.postMessage({ ok: true, ms: Math.round(performance.now() - started) } satisfies SqlRunResult);
    } catch (e) {
      self.postMessage({
        ok: false,
        phase: "boot",
        error: e instanceof Error ? e.message : String(e),
      } satisfies SqlRunResult);
    }
    return;
  }

  const { setup, sql, verify } = event.data;
  let phase: SqlRunResult["phase"] = "boot";

  try {
    const db = await getDb();

    // Each run starts from a clean slate: a candidate who ran their
    // statement twice would otherwise see the second run fail against
    // state their own first run created.
    phase = "setup";
    await db.exec("DROP SCHEMA public CASCADE; CREATE SCHEMA public;");
    for (const statement of setup) {
      await db.exec(statement);
    }

    phase = "candidate";
    await db.exec(sql);

    phase = "verify";
    const result = await db.query(verify);

    self.postMessage({
      ok: true,
      rows: (result.rows as Record<string, unknown>[]).map((row) => Object.values(row)),
      columns: result.fields.map((f) => f.name),
      ms: Math.round(performance.now() - started),
    } satisfies SqlRunResult);
  } catch (e) {
    self.postMessage({
      ok: false,
      phase,
      error: e instanceof Error ? e.message : String(e),
      ms: Math.round(performance.now() - started),
    } satisfies SqlRunResult);
  }
};
