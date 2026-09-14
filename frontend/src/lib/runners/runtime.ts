// Loads the WASM runtimes that execute a candidate's code, without ever
// getting in the way of the interview itself.
//
// The rules this exists to enforce:
//
//   1. Nothing downloads on any page that will not run code. A visitor to
//      the landing page, and every HR, IB or conversation-only interview,
//      fetches none of it.
//   2. Warming happens in the BACKGROUND during the conversation round, so
//      by the time the editor opens the runtime is already booted.
//   3. Warming is strictly secondary. It waits for the browser to be idle
//      and yields to anything else in flight -- the live audio socket must
//      never stutter because we were speculatively downloading Postgres.
//   4. If the round opens before warming finished, it finishes then, with
//      progress on screen rather than a frozen editor.

export type RuntimeKind = "sql" | "python" | "javascript";

export type RuntimeStatus = "cold" | "warming" | "ready" | "failed";

interface RuntimeState {
  status: RuntimeStatus;
  /** Shared so a warm-up already in flight is awaited rather than restarted. */
  promise: Promise<Worker> | null;
  worker: Worker | null;
  error?: string;
}

const states: Record<RuntimeKind, RuntimeState> = {
  sql: { status: "cold", promise: null, worker: null },
  python: { status: "cold", promise: null, worker: null },
  javascript: { status: "cold", promise: null, worker: null },
};

const listeners = new Set<() => void>();

function notify() {
  for (const listener of listeners) listener();
}

export function subscribeToRuntimes(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function runtimeStatus(kind: RuntimeKind): RuntimeStatus {
  return states[kind].status;
}

/**
 * Which runtime, if any, a round of this format and language needs.
 *
 * Java and C/C++ return null on purpose: neither has a credible browser
 * runtime, so their Run goes to the server for an assessment instead.
 */
export function runtimeForFormat(format: string, language?: string | null): RuntimeKind | null {
  if (format === "SQL") return "sql";
  if (format !== "CODE") return null;
  if (language === "python") return "python";
  if (language === "javascript") return "javascript";
  return null;
}

/** True when this language runs in the browser rather than on the server. */
export function runsInBrowser(format: string, language?: string | null): boolean {
  return runtimeForFormat(format, language) !== null;
}

/** Resolves when the browser is doing nothing more important. */
function whenIdle(timeout = 4000): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window === "undefined") return resolve();
    const ric = (window as unknown as { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number })
      .requestIdleCallback;
    // The timeout is a ceiling, not a target: it guarantees we eventually
    // warm up even on a page that never goes fully idle.
    if (ric) ric(() => resolve(), { timeout });
    else setTimeout(resolve, timeout);
  });
}

function spawn(kind: RuntimeKind): Worker {
  // Static URLs, not a computed path: the bundler has to see each worker
  // at build time to emit it as its own chunk.
  switch (kind) {
    case "sql":
      return new Worker(new URL("./sql.worker.ts", import.meta.url), { type: "module" });
    case "python":
      return new Worker(new URL("./python.worker.ts", import.meta.url), { type: "module" });
    case "javascript":
      return new Worker(new URL("./javascript.worker.ts", import.meta.url), { type: "module" });
  }
}

/**
 * Boots a runtime, sharing one attempt across every caller.
 *
 * `background` runs it behind an idle callback; a foreground call (the
 * round actually starting) skips the wait and joins whatever is already
 * in flight.
 */
function ensure(kind: RuntimeKind, background: boolean): Promise<Worker> {
  const state = states[kind];
  if (state.promise) return state.promise;

  state.status = "warming";
  notify();

  state.promise = (async () => {
    if (background) await whenIdle();

    const worker = spawn(kind);
    await new Promise<void>((resolve, reject) => {
      const onMessage = (event: MessageEvent<{ ok: boolean; error?: string }>) => {
        worker.removeEventListener("message", onMessage);
        if (event.data.ok) resolve();
        else reject(new Error(event.data.error ?? "runtime failed to start"));
      };
      worker.addEventListener("message", onMessage);
      worker.addEventListener("error", (e) => reject(new Error(e.message)), { once: true });
      worker.postMessage({ warmup: true });
    });

    state.worker = worker;
    state.status = "ready";
    notify();
    return worker;
  })();

  state.promise.catch((e: unknown) => {
    state.status = "failed";
    state.error = e instanceof Error ? e.message : String(e);
    // Cleared so a later foreground attempt can retry rather than
    // inheriting a failure that may have been a flaky network.
    state.promise = null;
    notify();
  });

  return state.promise;
}

/**
 * Warm a runtime in the background. Fire and forget.
 *
 * Deliberately swallows failures: a speculative warm-up that fails must
 * never surface an error mid-interview. The foreground path will retry and
 * report properly if the round actually needs it.
 */
export function warmRuntime(kind: RuntimeKind): void {
  if (typeof window === "undefined") return;
  if (states[kind].status === "ready" || states[kind].promise) return;
  void ensure(kind, true).catch(() => {});
}

/** Get a runtime, waiting for it, for a round that needs it now. */
export function getRuntime(kind: RuntimeKind): Promise<Worker> {
  return ensure(kind, false);
}

/**
 * Kill one runtime.
 *
 * The only way to stop synchronous code that will not stop on its own, so
 * a runaway loop costs the candidate a re-boot rather than the round.
 */
export function disposeRuntime(kind: RuntimeKind): void {
  const state = states[kind];
  state.worker?.terminate();
  state.worker = null;
  state.promise = null;
  state.status = "cold";
  notify();
}

/**
 * Runs code against a set of cases and returns the per-case outcome.
 *
 * Shared by the Run button (visible cases only, for self-check) and by
 * submit (every case, including hidden ones whose expected values the
 * browser was never given). One implementation so the two can never
 * disagree about how a case is executed.
 */
export async function runCode(
  kind: RuntimeKind,
  payload: { kind: "call" | "ops"; entry: string; code: string; cases: unknown[] },
  timeoutMs = 10000,
): Promise<{ ok: boolean; results?: { name: string; passed: boolean; got?: string; expected: string; error?: string }[]; error?: string; phase?: string }> {
  const worker = await getRuntime(kind);
  return new Promise((resolve, reject) => {
    const onMessage = (event: MessageEvent) => {
      clearTimeout(timer);
      worker.removeEventListener("message", onMessage);
      resolve(event.data);
    };
    // Terminating the worker is the only way to stop synchronous code that
    // will not stop on its own. The runtime is dropped so the next run
    // boots a clean one -- a runaway loop costs a reboot, not the round.
    const timer = setTimeout(() => {
      worker.removeEventListener("message", onMessage);
      disposeRuntime(kind);
      reject(new Error("Your code ran for too long and was stopped — check for an infinite loop."));
    }, timeoutMs);
    worker.addEventListener("message", onMessage);
    worker.postMessage(payload);
  });
}

/** Frees the WASM heap once an interview is over. */
export function disposeRuntimes(): void {
  for (const kind of Object.keys(states) as RuntimeKind[]) {
    const state = states[kind];
    state.worker?.terminate();
    state.worker = null;
    state.promise = null;
    state.status = "cold";
  }
  notify();
}
