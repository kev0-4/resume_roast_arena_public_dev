"""
The gate that stops a question shipping with test cases that grade nothing.

Every CODE and SQL question in the catalogue is run here against a
reference solution (which must pass everything) and a deliberately broken
one (which must fail something). A question whose cases cannot tell those
two apart is not a test, and a candidate graded against it has no
recourse.

This exists because PR #20 shipped exactly that: the rate limiter's cases
passed a solution that wrongly recorded refused requests, because the
offending timestamp had aged out before it mattered. It was caught by
writing a broken solution by hand -- which does not scale past a handful
of questions.

The Python runner below is a faithful port of the DRIVER in
frontend/src/lib/runners/python.worker.ts. It has to be: if the two
disagree, this gate proves something about a harness the candidate never
actually runs. The normalisation rules (tuple/list equivalence, an
integral float equal to its int) and the JSON comparison are copied
deliberately rather than improved on.

SQL runs against the real Postgres the suite already has, in a throwaway
schema dropped afterwards -- the same engine the questions were written
for, so MERGE and window functions behave as they will in the browser's
PGlite.
"""

import asyncio
import datetime
import decimal
import json

import pytest
from sqlalchemy import text

from .catalogue import load_catalogue, public_question
from .catalogue.solutions import SOLUTIONS

CODE_FORMATS = {"CODE", "SQL"}


def _code_questions():
    return [q for q in load_catalogue() if q["format"] == "CODE"]


def _sql_questions():
    return [q for q in load_catalogue() if q["format"] == "SQL"]


# ---------------------------------------------------------------------------
# Python runner -- a faithful port of python.worker.ts's DRIVER
# ---------------------------------------------------------------------------


def _normalise(value):
    if isinstance(value, (tuple, list)):
        return [_normalise(v) for v in value]
    if isinstance(value, dict):
        return {k: _normalise(v) for k, v in value.items()}
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def run_python_case(code: str, kind: str, entry: str, case: dict) -> tuple[bool, str]:
    """Returns (passed, detail). Mirrors the worker's per-case behaviour."""
    namespace: dict = {}
    exec(compile(code, "<solution>", "exec"), namespace)  # noqa: S102 - our own code

    target = namespace.get(entry)
    if target is None:
        return False, f"no {entry} defined"

    expected = _normalise(case["expected"])
    try:
        if kind == "call":
            got = _normalise(target(*case.get("args", [])))
        else:
            instance = target(*case.get("construct", []))
            got = []
            for method, args in case.get("ops", []):
                got.append(_normalise(getattr(instance, method)(*args)))
    except Exception as exc:  # the worker reports these as a failed case too
        return False, f"{type(exc).__name__}: {exc}"

    passed = json.dumps(got, sort_keys=True) == json.dumps(expected, sort_keys=True)
    return passed, f"got {json.dumps(got)} expected {json.dumps(expected)}"


def run_python_solution(code: str, question: dict) -> list[tuple[str, bool, bool, str]]:
    """[(case_name, hidden, passed, detail)] for every case in the harness."""
    harness = question["harness"]
    entry = harness["entry"]["python"]
    out = []
    for index, case in enumerate(harness["cases"]):
        name = case.get("name") or f"case {index + 1}"
        passed, detail = run_python_case(code, harness["kind"], entry, case)
        out.append((name, bool(case.get("hidden")), passed, detail))
    return out


# ---------------------------------------------------------------------------
# SQL runner -- real Postgres, throwaway schema
# ---------------------------------------------------------------------------


def _normalise_sql(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (datetime.datetime, datetime.date)):
        return str(value)
    if isinstance(value, decimal.Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


async def _run_sql_solution(question: dict, answer: str) -> list[list]:
    from ..db.session import AsyncSessionLocal

    harness = question["harness"]
    schema = f"qgate_{question['id'].replace('-', '_')}"

    async with AsyncSessionLocal() as db:
        await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await db.execute(text(f'CREATE SCHEMA "{schema}"'))
        await db.commit()
        try:
            await db.execute(text(f'SET search_path TO "{schema}"'))
            for statement in harness["setup"]:
                await db.execute(text(statement))

            if harness.get("wrap_candidate_as_view"):
                await db.execute(text(f"CREATE VIEW candidate_answer AS {answer.strip().rstrip(';')}"))
            else:
                for statement in filter(None, (s.strip() for s in answer.split(";"))):
                    await db.execute(text(statement))

            rows = (await db.execute(text(harness["verify"]))).fetchall()
            return [[_normalise_sql(v) for v in row] for row in rows]
        finally:
            await db.rollback()
            async with AsyncSessionLocal() as cleanup:
                await cleanup.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
                await cleanup.commit()


def run_sql_solution(question: dict, answer: str) -> list[list]:
    async def wrapped():
        from ..db.session import engine

        try:
            return await _run_sql_solution(question, answer)
        finally:
            await engine.dispose()

    return asyncio.run(wrapped())


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


class TestEveryGradedQuestionHasSolutions:
    """A new question cannot ship without the means to check its own cases."""

    @pytest.mark.parametrize("question", _code_questions() + _sql_questions(), ids=lambda q: q["id"])
    def test_has_a_reference_and_a_broken_solution(self, question):
        entry = SOLUTIONS.get(question["id"])
        assert entry is not None, (
            f"{question['id']} is graded but has no entry in solutions.py. "
            "Every CODE and SQL question needs a reference and a broken solution "
            "so its cases can be proven to discriminate."
        )
        assert entry.get("reference", "").strip(), f"{question['id']} has no reference solution"
        assert entry.get("broken", "").strip(), f"{question['id']} has no broken solution"

    def test_no_solution_for_a_question_that_does_not_exist(self):
        # A renamed or deleted question must not leave a stale answer key.
        known = {q["id"] for q in load_catalogue()}
        assert set(SOLUTIONS) <= known, f"solutions.py names unknown questions: {set(SOLUTIONS) - known}"

    def test_solutions_never_reach_the_candidate(self):
        """
        The whole reason solutions live outside questions.json.

        Compares against the BODY of each solution, not its signature: a
        starter legitimately contains `def merge_intervals(...)` and a
        schema legitimately names the same tables the answer does. What
        must never appear is a line that only a working solution has.
        """
        def field_names(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    yield key
                    yield from field_names(value)
            elif isinstance(node, list):
                for item in node:
                    yield from field_names(item)

        for question in load_catalogue():
            public = public_question(question)
            serialized = json.dumps(public)
            entry = SOLUTIONS.get(question["id"], {})

            # The realistic leak: someone adds a solution field to
            # questions.json and public_question forgets to strip it.
            leaked = {"reference", "broken", "sneaky", "solution", "answer_key"} & set(field_names(public))
            assert not leaked, f"{question['id']}: solution-shaped field(s) {leaked} reach the candidate"

            for variant in ("reference", "broken", "sneaky"):
                body = (entry.get(variant) or "").strip()
                if not body:
                    continue
                # Whole-body check. A single line is not enough to assert on:
                # a SQL reference legitimately restates the prompt's own
                # wording ("is_current = false" is in the specification), so
                # line matching produces false alarms on exactly the
                # questions where the spec is precise.
                assert body not in serialized, (
                    f"{question['id']}: the {variant} solution reaches the candidate verbatim"
                )

                # Three consecutive lines of real logic is a leak, not a
                # coincidence -- and this still catches a partial paste.
                lines = [ln.strip() for ln in body.splitlines() if len(ln.strip()) >= 12]
                for i in range(len(lines) - 2):
                    window = "\n".join(lines[i:i + 3])
                    normalised = " ".join(window.split())
                    assert normalised not in " ".join(serialized.split()), (
                        f"{question['id']}: three consecutive lines of the {variant} "
                        f"solution reach the candidate -- {window!r}"
                    )


class TestPythonReferenceSolutions:
    @pytest.mark.parametrize("question", _code_questions(), ids=lambda q: q["id"])
    def test_reference_passes_every_case(self, question):
        results = run_python_solution(SOLUTIONS[question["id"]]["reference"], question)
        failed = [(n, d) for n, _h, passed, d in results if not passed]
        assert not failed, (
            f"{question['id']}: the reference solution fails its own cases, so the "
            f"EXPECTED VALUES are wrong and every candidate is graded against them. {failed}"
        )

    @pytest.mark.parametrize("question", _code_questions(), ids=lambda q: q["id"])
    def test_broken_solution_is_actually_caught(self, question):
        results = run_python_solution(SOLUTIONS[question["id"]]["broken"], question)
        assert any(not passed for _n, _h, passed, _d in results), (
            f"{question['id']}: a deliberately broken solution passes every case. "
            "These cases grade nothing."
        )

    @pytest.mark.parametrize("question", _code_questions(), ids=lambda q: q["id"])
    def test_every_code_question_has_hidden_cases(self, question):
        hidden = [c for c in question["harness"]["cases"] if c.get("hidden")]
        assert hidden, (
            f"{question['id']} has no hidden cases, so tweaking until Run goes green "
            "is enough to pass it."
        )

    @pytest.mark.parametrize(
        "question",
        [q for q in _code_questions() if SOLUTIONS.get(q["id"], {}).get("sneaky")],
        ids=lambda q: q["id"],
    )
    def test_hidden_cases_earn_their_keep(self, question):
        """The sneaky variant passes everything Run would show and is caught anyway."""
        results = run_python_solution(SOLUTIONS[question["id"]]["sneaky"], question)
        visible_failures = [n for n, hidden, passed, _d in results if not hidden and not passed]
        hidden_failures = [n for n, hidden, passed, _d in results if hidden and not passed]

        assert not visible_failures, (
            f"{question['id']}: the sneaky solution fails a VISIBLE case ({visible_failures}), "
            "so it proves nothing about the hidden ones. Make it pass Run first."
        )
        assert hidden_failures, (
            f"{question['id']}: a solution that passes every visible case also passes every "
            "hidden one. The hidden cases add no signal beyond Run."
        )


class TestSqlReferenceSolutions:
    @pytest.mark.parametrize("question", _sql_questions(), ids=lambda q: q["id"])
    def test_reference_produces_the_expected_rows(self, question):
        got = run_sql_solution(question, SOLUTIONS[question["id"]]["reference"])
        expected = [[_normalise_sql(v) for v in row] for row in question["harness"]["expected"]]
        assert got == expected, (
            f"{question['id']}: the reference SQL does not produce the expected rows, so the "
            f"expected values are wrong.\n  got:      {got}\n  expected: {expected}"
        )

    @pytest.mark.parametrize("question", _sql_questions(), ids=lambda q: q["id"])
    def test_broken_sql_is_actually_caught(self, question):
        got = run_sql_solution(question, SOLUTIONS[question["id"]]["broken"])
        expected = [[_normalise_sql(v) for v in row] for row in question["harness"]["expected"]]
        assert got != expected, f"{question['id']}: deliberately broken SQL produces the expected rows."


class TestMcqIntegrity:
    """MCQ is auto-scored with no model in the loop, so a bad key is a silent wrong grade."""

    @pytest.mark.parametrize(
        "question",
        [q for q in load_catalogue() if q["format"] == "MCQ"],
        ids=lambda q: q["id"],
    )
    def test_answer_keys_are_sane(self, question):
        for index, item in enumerate(question["questions"]):
            options = item["options"]
            where = f"{question['id']} q{index + 1}"
            assert len(options) >= 2, f"{where}: needs at least two options"
            assert isinstance(item["answer"], int), f"{where}: answer must be an index"
            assert 0 <= item["answer"] < len(options), f"{where}: answer index out of range"
            assert len(set(options)) == len(options), f"{where}: duplicate option text"
            assert item.get("why", "").strip(), f"{where}: needs a `why` -- it is shown in the debrief"
