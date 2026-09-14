// Runs the candidate's Python, in a Web Worker, via Pyodide.
//
// A worker for the same reason SQL uses one: booting CPython is several
// megabytes of WASM and a heavy init, and the main thread is carrying the
// live audio socket. It also means an infinite loop can be killed by
// terminating the worker, which is the only reliable way to stop runaway
// synchronous code in a browser.
//
// Pyodide comes from jsDelivr rather than our bundle: the npm package is
// ~14MB unpacked and would bloat every deploy for a runtime most
// interviews never touch. The version is pinned -- "latest" would mean an
// upstream release could silently change how candidates' code behaves.

const PYODIDE_VERSION = "v0.28.0";
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/${PYODIDE_VERSION}/full/`;

export interface CodeCase {
  name?: string;
  /** "call" shape. */
  args?: unknown[];
  /** "ops" shape. */
  construct?: unknown[];
  ops?: [string, unknown[]][];
  expected: unknown;
}

export interface CodeRunRequest {
  kind: "call" | "ops";
  entry: string;
  code: string;
  cases: CodeCase[];
}

export interface CaseResult {
  name: string;
  passed: boolean;
  got?: string;
  expected: string;
  error?: string;
}

export interface CodeRunResult {
  ok: boolean;
  results?: CaseResult[];
  error?: string;
  phase?: "boot" | "define" | "run";
  ms?: number;
}

declare function importScripts(...urls: string[]): void;
declare const loadPyodide: (options: { indexURL: string }) => Promise<PyodideApi>;

interface PyodideApi {
  runPython: (code: string) => unknown;
  globals: { set: (name: string, value: unknown) => void };
}

let pyodidePromise: Promise<PyodideApi> | null = null;

function getPyodide(): Promise<PyodideApi> {
  if (!pyodidePromise) {
    pyodidePromise = (async () => {
      importScripts(`${PYODIDE_URL}pyodide.js`);
      return await loadPyodide({ indexURL: PYODIDE_URL });
    })();
  }
  return pyodidePromise;
}

/**
 * The driver, written in Python because comparing results is far more
 * reliable inside the interpreter than marshalling every value out.
 *
 * Results are compared as JSON so a tuple and a list, or an int and a
 * float that are equal, do not fail a candidate on a representation
 * detail they were never asked about.
 */
const DRIVER = `
import json

def __rr_normalise(value):
    if isinstance(value, tuple):
        return [__rr_normalise(v) for v in value]
    if isinstance(value, list):
        return [__rr_normalise(v) for v in value]
    if isinstance(value, dict):
        return {k: __rr_normalise(v) for k, v in value.items()}
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value

def __rr_run(kind, entry, cases_json):
    cases = json.loads(cases_json)
    target = globals().get(entry)
    if target is None:
        return json.dumps({"ok": False, "phase": "define",
                           "error": "No " + entry + " was defined. Check the name matches the starter code."})
    out = []
    for index, case in enumerate(cases):
        name = case.get("name") or ("case " + str(index + 1))
        expected = __rr_normalise(case["expected"])
        try:
            if kind == "call":
                got = __rr_normalise(target(*case.get("args", [])))
            else:
                instance = target(*case.get("construct", []))
                got = []
                for method, args in case.get("ops", []):
                    got.append(__rr_normalise(getattr(instance, method)(*args)))
            out.append({
                "name": name,
                "passed": json.dumps(got, sort_keys=True) == json.dumps(expected, sort_keys=True),
                "got": json.dumps(got),
                "expected": json.dumps(expected),
            })
        except Exception as exc:
            out.append({
                "name": name,
                "passed": False,
                "expected": json.dumps(expected),
                "error": type(exc).__name__ + ": " + str(exc),
            })
    return json.dumps({"ok": True, "results": out})
`;

self.onmessage = async (event: MessageEvent<CodeRunRequest | { warmup: true }>) => {
  const started = performance.now();

  if ("warmup" in event.data) {
    try {
      await getPyodide();
      self.postMessage({ ok: true, ms: Math.round(performance.now() - started) } satisfies CodeRunResult);
    } catch (e) {
      self.postMessage({
        ok: false,
        phase: "boot",
        error: e instanceof Error ? e.message : String(e),
      } satisfies CodeRunResult);
    }
    return;
  }

  const { kind, entry, code, cases } = event.data;
  try {
    const pyodide = await getPyodide();

    // The candidate's code and the driver are run separately so a syntax
    // error in theirs is reported as theirs.
    try {
      pyodide.runPython(code);
    } catch (e) {
      self.postMessage({
        ok: false,
        phase: "define",
        error: e instanceof Error ? e.message : String(e),
        ms: Math.round(performance.now() - started),
      } satisfies CodeRunResult);
      return;
    }

    pyodide.runPython(DRIVER);
    pyodide.globals.set("__rr_kind", kind);
    pyodide.globals.set("__rr_entry", entry);
    pyodide.globals.set("__rr_cases", JSON.stringify(cases));
    const raw = pyodide.runPython("__rr_run(__rr_kind, __rr_entry, __rr_cases)") as string;
    const parsed = JSON.parse(raw) as CodeRunResult;

    self.postMessage({ ...parsed, ms: Math.round(performance.now() - started) } satisfies CodeRunResult);
  } catch (e) {
    self.postMessage({
      ok: false,
      phase: "run",
      error: e instanceof Error ? e.message : String(e),
      ms: Math.round(performance.now() - started),
    } satisfies CodeRunResult);
  }
};
