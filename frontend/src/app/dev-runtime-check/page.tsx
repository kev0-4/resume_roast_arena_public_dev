"use client";

// Dev-only test surface for scripts/interview_smoke_test/runtime_check.py.
//
// Reaching round-stage.tsx to test Pyodide/PGlite meant going through a
// real live conversation first, which turned into its own rabbit hole
// (see code_editor_check.py's comments and the session history: a text-
// only nudge sent while the model was speaking went unanswered, and a
// looping fake-mic audio file drowned the text channel in continuous
// false "activity" even during genuinely quiet moments). None of that
// has anything to do with whether the WASM runtimes actually work.
//
// This page decouples the two questions entirely: it imports the same
// runner code round-stage.tsx uses and exposes it on `window`, so a
// script can call runCode() directly -- real Pyodide, real PGlite, real
// Worker -- with zero live interview, zero auth, zero Gemini involved.
//
// Gated on NODE_ENV, same pattern as firebase.ts's __TEST_AUTH__ and
// use-live-interview.ts's __TEST_LIVE__: a no-op in any production build.

import { useEffect } from "react";
import { getRuntime, runCode, runtimeForFormat, warmRuntime, type RuntimeKind } from "@/lib/runners/runtime";
import type { SqlRunRequest, SqlRunResult } from "@/lib/runners/sql.worker";

// SQL never went through runCode -- SqlRunPanel talks to its worker
// directly with a different message shape ({setup, sql, verify} rather
// than {kind, entry, code, cases}). Mirrors that exact call, not a
// simplification of it.
async function runSql(request: SqlRunRequest): Promise<SqlRunResult> {
  const worker = await getRuntime("sql");
  return new Promise((resolve, reject) => {
    const onMessage = (event: MessageEvent<SqlRunResult>) => {
      worker.removeEventListener("message", onMessage);
      resolve(event.data);
    };
    worker.addEventListener("message", onMessage);
    const timer = setTimeout(() => {
      worker.removeEventListener("message", onMessage);
      reject(new Error("Query took longer than 15 seconds and was stopped."));
    }, 15000);
    const done = () => clearTimeout(timer);
    worker.addEventListener("message", done, { once: true });
    worker.postMessage(request);
  });
}

export default function DevRuntimeCheckPage() {
  useEffect(() => {
    if (process.env.NODE_ENV === "production") return;
    (window as unknown as { __TEST_RUNTIME__: unknown }).__TEST_RUNTIME__ = {
      runCode,
      runSql,
      runtimeForFormat,
      warmRuntime: (kind: RuntimeKind) => warmRuntime(kind),
    };
  }, []);

  if (process.env.NODE_ENV === "production") return null;

  // Readiness is checked directly (window.__TEST_RUNTIME__ existing),
  // not through this render -- nothing here needs to be reactive state.
  return (
    <div style={{ padding: 24, fontFamily: "monospace", fontSize: 13 }}>
      <p>dev-only runtime test surface -- not part of the product.</p>
    </div>
  );
}
