"""
scripts/interview_smoke_test/runtime_check.py

Ad hoc, on-demand check that the browser's code-execution runtime
(Pyodide, real WASM CPython) actually works -- decoupled entirely from
the live interview, which turned into its own rabbit hole (see
code_editor_check.py's docstring and the session history) for a reason
that has nothing to do with this question: reaching the exercise round
needed a live conversation to cooperate, and whether Pyodide correctly
executes code doesn't depend on that at all.

Drives frontend/src/app/dev-runtime-check, a dev-only page that imports
the SAME runner code round-stage.tsx uses (frontend/src/lib/runners/
runtime.ts's runCode) and exposes it on window -- real Pyodide, real
Worker, zero interview, zero auth, zero Gemini involved.

For every CODE question in the catalogue: runs the REFERENCE solution
(must pass every case, visible and hidden) and the BROKEN one (must fail
something) THROUGH THE ACTUAL BROWSER RUNTIME. This is deliberately the
same pair backend/src/interview/test_catalogue_solutions.py already
proves correct via Python's own exec() -- running them again here checks
something that gate cannot: does Pyodide's compiled CPython agree with
real CPython, not just whether the reference solution is right.

NEEDS: frontend dev server on :3000 (no backend, no auth required at all).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))
from src.interview.catalogue import load_catalogue  # noqa: E402
from src.interview.catalogue.solutions import SOLUTIONS  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

FRONTEND_URL = "http://localhost:3000"


class Report:
    def __init__(self) -> None:
        self.lines: list[tuple[str, bool, str]] = []

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}{' -- ' + detail if detail else ''}")
        self.lines.append((label, ok, detail))

    def summary(self) -> bool:
        print("\n" + "=" * 70 + "\nSUMMARY\n" + "=" * 70)
        all_ok = True
        for label, ok, _ in self.lines:
            print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
            all_ok = all_ok and ok
        print("=" * 70, "\nALL PASSED" if all_ok else "\nSOME FAILED -- see above")
        return all_ok


def _normalise_row(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and len(value) >= 19 and value[4] == "-" and "T" in value[:11]:
        return value[:19].replace("T", " ")  # ISO date -> the same truncated form run-panel.tsx compares
    return str(value).strip() if not isinstance(value, (int, float)) else value


def _rows_match(got: list, expected: list) -> bool:
    if len(got) != len(expected):
        return False
    return all(
        len(g) == len(e) and all(_normalise_row(gv) == _normalise_row(ev) for gv, ev in zip(g, e))
        for g, e in zip(got, expected)
    )


def _check_sql(page, report: Report, question: dict) -> None:
    question_id = question["id"]
    entry = SOLUTIONS.get(question_id)
    if entry is None:
        report.check(f"{question_id}: has a reference solution", False, "not in SOLUTIONS")
        return

    harness = question["harness"]
    for variant_name, must_match in (("reference", True), ("broken", False)):
        sql = entry.get(variant_name)
        if not sql:
            continue
        candidate_sql = (
            f'CREATE VIEW candidate_answer AS {sql.strip().rstrip(";")};'
            if harness.get("wrap_candidate_as_view")
            else sql
        )
        result = page.evaluate(
            "(req) => window.__TEST_RUNTIME__.runSql(req)",
            {"setup": harness["setup"], "sql": candidate_sql, "verify": harness["verify"]},
        )
        if not result.get("ok"):
            report.check(
                f"{question_id} [{variant_name}]: ran without a runtime error",
                False,
                f"phase={result.get('phase')} error={result.get('error')}",
            )
            continue
        matched = _rows_match(result.get("rows") or [], harness["expected"])
        label = f"{question_id} [{variant_name}] via real PGlite: rows {'match' if matched else 'do NOT match'} expected"
        report.check(label, matched if must_match else not matched)


def main() -> int:
    report = Report()
    code_questions = [q for q in load_catalogue() if q["format"] == "CODE"]
    sql_questions = [q for q in load_catalogue() if q["format"] == "SQL"]
    print(f"[setup] {len(code_questions)} CODE questions, {len(sql_questions)} SQL questions")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda exc: print(f"  [pageerror] {exc}"))

        print("[browser] loading the dev runtime-check page...")
        page.goto(f"{FRONTEND_URL}/dev-runtime-check")
        page.wait_for_function("() => !!window.__TEST_RUNTIME__", timeout=15000)
        report.check("dev-runtime-check page loaded and hook is ready", True)

        for question in code_questions:
            question_id = question["id"]
            entry = SOLUTIONS.get(question_id)
            if entry is None:
                report.check(f"{question_id}: has a reference solution", False, "not in SOLUTIONS")
                continue

            harness = question["harness"]
            language = entry.get("language", "python")
            runtime_kind = "python" if language == "python" else "javascript"
            entry_name = harness["entry"].get(language)
            if not entry_name:
                report.check(f"{question_id}: has a {language} entry point", False)
                continue

            for variant_name, must_all_pass in (("reference", True), ("broken", False)):
                code = entry.get(variant_name)
                if not code:
                    continue
                result = page.evaluate(
                    "([kind, payload]) => window.__TEST_RUNTIME__.runCode(kind, payload, 20000)",
                    [runtime_kind, {"kind": harness["kind"], "entry": entry_name, "code": code, "cases": harness["cases"]}],
                )
                if not result.get("ok"):
                    report.check(
                        f"{question_id} [{variant_name}]: ran without a runtime error",
                        False,
                        f"phase={result.get('phase')} error={result.get('error')}",
                    )
                    continue
                results = result.get("results") or []
                all_passed = bool(results) and all(r["passed"] for r in results)
                passed_count = sum(1 for r in results if r["passed"])
                label = f"{question_id} [{variant_name}] via real Pyodide: {passed_count}/{len(results)} cases passed"
                if variant_name == "reference":
                    report.check(label, all_passed, "every case must pass" if not all_passed else "")
                else:
                    report.check(label + " (must NOT be all-passing)", not all_passed)

        for question in sql_questions:
            _check_sql(page, report, question)

        browser.close()

    return 0 if report.summary() else 1


if __name__ == "__main__":
    raise SystemExit(main())
