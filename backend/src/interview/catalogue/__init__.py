"""
backend/src/interview/catalogue/

The question bank, shipped as data rather than generated.

Generated questions were considered and rejected: a hallucinated MCQ with
two defensible answers, or a coding problem whose stated constraints
contradict its own rubric, is far worse than a smaller bank -- it is scored
against the candidate and they have no recourse. The planner therefore
CHOOSES from this file and never writes a question.

A round's answering surface differs by `format`, but every entry carries
the same core fields so the planner sees one shape:

    CODE     prompt + per-language starter, graded by a text review
    SQL      prompt + schema shown on screen, graded by a text review
    WRITTEN  prompt only, free text, graded by a text review
    MCQ      a list of questions with a correct index, auto-scored

`verticals` is advisory: it is what the planner matches against, but the
model infers the candidate's vertical itself rather than us maintaining an
enum, so an unanticipated role still gets a sensible pick.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

_QUESTIONS_PATH = Path(__file__).parent / "questions.json"

FORMATS = ("CODE", "SQL", "WRITTEN", "MCQ")
# Everything the editor is wired for. SQL is deliberately NOT here: it is a
# format, not a language, because a SQL question is unanswerable without its
# schema on screen.
CODE_LANGUAGES = ("python", "javascript", "java", "cpp")


class CatalogueError(ValueError):
    """A question in the bank is malformed. Raised at import, not at runtime."""


def _validate(entry: Dict[str, Any], index: int) -> None:
    where = f"questions.json[{index}] (id={entry.get('id', '?')!r})"

    for field in ("id", "format", "verticals", "topics", "difficulty", "minutes"):
        if field not in entry:
            raise CatalogueError(f"{where}: missing required field {field!r}")

    if entry["format"] not in FORMATS:
        raise CatalogueError(f"{where}: unknown format {entry['format']!r}, expected one of {FORMATS}")

    if entry["format"] == "MCQ":
        questions = entry.get("questions")
        if not questions:
            raise CatalogueError(f"{where}: MCQ entry has no questions")
        for q_index, question in enumerate(questions):
            options = question.get("options") or []
            answer = question.get("answer")
            if len(options) < 2:
                raise CatalogueError(f"{where} q{q_index}: needs at least two options")
            # The bug that matters: an answer index pointing at nothing would
            # mark every candidate wrong, silently and unappealably.
            if not isinstance(answer, int) or not (0 <= answer < len(options)):
                raise CatalogueError(
                    f"{where} q{q_index}: answer {answer!r} is not a valid index into {len(options)} options"
                )
    else:
        if not entry.get("prompt"):
            raise CatalogueError(f"{where}: non-MCQ entry needs a prompt")
        if not entry.get("rubric"):
            raise CatalogueError(f"{where}: non-MCQ entry needs a rubric to grade against")

    if entry["format"] == "CODE" and not entry.get("starter"):
        raise CatalogueError(f"{where}: CODE entry needs starter code")
    if entry["format"] == "SQL" and not entry.get("schema"):
        raise CatalogueError(f"{where}: SQL entry needs a schema -- it is unanswerable without one")


@lru_cache(maxsize=1)
def load_catalogue() -> List[Dict[str, Any]]:
    """Every question, validated. Cached: the file never changes at runtime."""
    entries = json.loads(_QUESTIONS_PATH.read_text())

    seen = set()
    for index, entry in enumerate(entries):
        _validate(entry, index)
        if entry["id"] in seen:
            raise CatalogueError(f"duplicate question id {entry['id']!r}")
        seen.add(entry["id"])

    return entries


def get_question(question_id: str) -> Dict[str, Any] | None:
    for entry in load_catalogue():
        if entry["id"] == question_id:
            return entry
    return None


def planner_index() -> List[Dict[str, Any]]:
    """
    The slim view handed to the planner.

    Deliberately excludes prompts, starters, schemas and -- critically --
    MCQ answer keys. The planner only needs enough to pick; sending the
    whole bank would be a larger prompt and would put correct answers into
    a response the client eventually sees.
    """
    return [
        {
            "id": entry["id"],
            "format": entry["format"],
            "verticals": entry["verticals"],
            "topics": entry["topics"],
            "difficulty": entry["difficulty"],
            "minutes": entry["minutes"],
        }
        for entry in load_catalogue()
    ]


def public_question(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    A question as the CANDIDATE may see it.

    Strips the rubric (which tells them exactly what the grader wants) and,
    for MCQ, the answer key and explanations. The client is untrusted; the
    answer key never leaves this process until the round is graded.
    """
    public = {
        "id": entry["id"],
        "format": entry["format"],
        "difficulty": entry["difficulty"],
        "topics": entry["topics"],
        "minutes": entry["minutes"],
    }
    if entry["format"] == "MCQ":
        public["questions"] = [
            {"prompt": q["prompt"], "options": q["options"]} for q in entry["questions"]
        ]
    else:
        public["prompt"] = entry["prompt"]
        # Worked examples and constraints are the difference between a
        # question you can answer and one you have to guess at.
        public["examples"] = entry.get("examples", [])
        public["constraints"] = entry.get("constraints", [])
    if entry["format"] == "CODE" and entry.get("harness"):
        harness = entry["harness"]
        # Hidden cases keep their INPUTS -- the code runs in the browser, so
        # they have to travel -- but never their expected output. The client
        # reports what it got and the server decides whether that is right,
        # so tweaking until the visible tests go green buys nothing.
        public["harness"] = {
            "kind": harness["kind"],
            "entry": harness["entry"],
            "cases": [
                {k: v for k, v in case.items() if not (case.get("hidden") and k == "expected")}
                for case in harness["cases"]
            ],
        }
    if entry["format"] == "CODE":
        public["starter"] = entry["starter"]
    if entry["format"] == "SQL":
        public["schema"] = entry["schema"]
        # The run harness ships to the client because running happens in
        # the candidate's own browser. Its expected rows are the same
        # information the worked examples already state on screen, so this
        # gives nothing away -- and the SCORE is never computed here: a
        # submission still goes to the server to be reviewed. The rubric,
        # which is what actually drives grading, stays server-side.
        if entry.get("harness"):
            public["harness"] = entry["harness"]
    return public
