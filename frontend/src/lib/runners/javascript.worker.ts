// Runs the candidate's JavaScript, in a Web Worker.
//
// No download at all, but still a worker -- for termination, not size. An
// infinite loop in the editor would otherwise lock the main thread and
// take the whole interview room with it, and there is no way to interrupt
// synchronous JS except by killing the context it runs in.
//
// A worker also gives a bare-ish global: no window, no DOM, no access to
// the page's Firebase session. That is not a security boundary against a
// determined author -- it is the candidate's own code in the candidate's
// own browser -- but it does keep an accident from reaching anything.

import type { CaseResult, CodeRunRequest, CodeRunResult } from "./python.worker";

/** JSON compare, so an array and a tuple-ish result do not differ on
 *  representation, and key order never decides a pass. */
function stable(value: unknown): string {
  return JSON.stringify(value, (_key, v) => {
    if (v && typeof v === "object" && !Array.isArray(v)) {
      return Object.fromEntries(Object.entries(v as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)));
    }
    return v === undefined ? null : v;
  });
}

self.onmessage = (event: MessageEvent<CodeRunRequest | { warmup: true }>) => {
  const started = performance.now();

  // Nothing to warm -- JS is already here. Answering keeps the loader's
  // contract identical across runtimes.
  if ("warmup" in event.data) {
    self.postMessage({ ok: true, ms: 0 } satisfies CodeRunResult);
    return;
  }

  const { kind, entry, code, cases } = event.data;

  let target: unknown;
  try {
    // Evaluated once; the entry point is read back out of the same scope.
    const factory = new Function(`${code}\n; return typeof ${entry} !== "undefined" ? ${entry} : undefined;`);
    target = factory();
  } catch (e) {
    self.postMessage({
      ok: false,
      phase: "define",
      error: e instanceof Error ? e.message : String(e),
      ms: Math.round(performance.now() - started),
    } satisfies CodeRunResult);
    return;
  }

  if (typeof target !== "function") {
    self.postMessage({
      ok: false,
      phase: "define",
      error: `No ${entry} was defined. Check the name matches the starter code.`,
      ms: Math.round(performance.now() - started),
    } satisfies CodeRunResult);
    return;
  }

  const results: CaseResult[] = cases.map((testCase, index) => {
    const name = testCase.name ?? `case ${index + 1}`;
    const expected = stable(testCase.expected);
    try {
      let got: unknown;
      if (kind === "call") {
        got = (target as (...args: unknown[]) => unknown)(...(testCase.args ?? []));
      } else {
        const Ctor = target as new (...args: unknown[]) => Record<string, (...args: unknown[]) => unknown>;
        const instance = new Ctor(...(testCase.construct ?? []));
        got = (testCase.ops ?? []).map(([method, args]) => {
          const fn = instance[method];
          if (typeof fn !== "function") throw new Error(`No method ${method} on ${entry}`);
          const value = fn.apply(instance, args);
          return value === undefined ? null : value;
        });
      }
      const gotJson = stable(got);
      return { name, passed: gotJson === expected, got: gotJson, expected };
    } catch (e) {
      return { name, passed: false, expected, error: e instanceof Error ? e.message : String(e) };
    }
  });

  self.postMessage({
    ok: true,
    results,
    ms: Math.round(performance.now() - started),
  } satisfies CodeRunResult);
};
