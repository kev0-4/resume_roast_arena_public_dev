"""
backend/src/interview/planner.py

Decides the shape of an interview before it starts: which rounds, in what
order, and which question from the catalogue.

One cheap structured text call at /start. Doing it up front rather than
mid-conversation buys three things: the candidate can be shown an agenda,
two runs of the same resume are comparable enough to sit on one
leaderboard, and the expensive live model never spends tokens deciding
logistics.

The planner picks a vertical itself rather than us maintaining an enum.
PR #16 established the model reads SWE / IB / quant resumes well enough to
grade them differently; a role nobody anticipated still gets a sensible
plan instead of an unhandled branch.

What it returns is NOT trusted. validate_plan below drops any question id
that isn't in the catalogue, clamps the round count, and falls back to a
conversation-only interview -- which is exactly what ships today and is
never a broken experience.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from .catalogue import get_question, planner_index

# An interview is a conversation plus at most this many exercise rounds.
# Two is already ~25 minutes with the debrief; more turns a mock interview
# into an exam.
MAX_EXERCISE_ROUNDS = 2
MIN_CONVERSATION_MINUTES = 5
MAX_CONVERSATION_MINUTES = 12


class PlannedRound(BaseModel):
    """
    kind is CONVERSATION or EXERCISE. An EXERCISE round names a
    question_id from the catalogue; a CONVERSATION round does not.
    """
    kind: str
    question_id: str
    minutes: int
    focus: str


class InterviewPlan(BaseModel):
    vertical: str
    rationale: str
    rounds: List[PlannedRound]


def build_planning_prompt(anonymized_resume_text: str, job_description: str) -> str:
    catalogue = planner_index()
    catalogue_lines = "\n".join(
        f"- {e['id']} | {e['format']} | {e['difficulty']} | {e['minutes']}min | "
        f"verticals: {', '.join(e['verticals'])} | topics: {', '.join(e['topics'])}"
        for e in catalogue
    )

    return f"""\
You are planning the structure of a mock interview. You are NOT conducting \
it and you are NOT writing questions -- you choose from a fixed catalogue.

---
CANDIDATE'S RESUME:

{anonymized_resume_text}

---
JOB DESCRIPTION:

{job_description.strip()}

---
AVAILABLE QUESTIONS:

{catalogue_lines}

---
TASK:

First, name the candidate's vertical in one or two lowercase words (for \
example: swe, etl, data, quant, ib, hr, consulting, product). Infer it from \
the resume and job description together -- the job description wins where \
they disagree, because that is the role being interviewed for.

Then plan the interview as a list of rounds.

- The FIRST round is always kind CONVERSATION, with question_id set to the \
empty string. This is the resume defence and it is the heart of the \
interview. Give it {MIN_CONVERSATION_MINUTES}-{MAX_CONVERSATION_MINUTES} minutes.
- Then add AT MOST {MAX_EXERCISE_ROUNDS} rounds of kind EXERCISE, each \
naming a question_id from the catalogue above and copying that question's \
stated minutes.
- Choose exercises that suit how this role is ACTUALLY interviewed. A \
software engineer writes code. A data or ETL engineer is tested on SQL \
before anything else. An investment banking or HR candidate should never \
be shown a code editor -- use MCQ and WRITTEN formats for them.
- If the role WRITES CODE OR SQL as a core part of the job -- any \
engineering role, any data or analytics role -- you should include at \
least one exercise. Someone interviewing for an engineering job expects \
to be asked to write something, and a conversation-only engineering \
interview will feel like the product forgot to test them.
- Plan ZERO exercise rounds only when the real interview for this role \
genuinely IS just a conversation and nothing in the catalogue fits -- for \
example a people or HR role with no listed MCQ or written question that \
suits it. Do not add an exercise just to have one, and never force a \
technical exercise onto a non-technical candidate.
- Never invent a question_id. Only ids listed above exist.

`focus` is one short sentence on why that round suits this candidate. \
`rationale` is one or two sentences explaining the overall shape.\
"""


def validate_plan(plan: InterviewPlan) -> InterviewPlan:
    """
    Makes whatever the model returned safe to run.

    Everything here has a fallback rather than an error: a candidate who
    has already waited for a resume roast should never be told the
    interview cannot start because the planner returned a bad id. The worst
    case degrades to a conversation-only interview, which is precisely the
    product that ships today.
    """
    rounds: List[PlannedRound] = []

    conversation_minutes = MIN_CONVERSATION_MINUTES
    for planned in plan.rounds:
        if planned.kind.upper() == "CONVERSATION":
            conversation_minutes = max(
                MIN_CONVERSATION_MINUTES, min(MAX_CONVERSATION_MINUTES, planned.minutes or 0)
            )
            break

    rounds.append(
        PlannedRound(
            kind="CONVERSATION",
            question_id="",
            minutes=conversation_minutes,
            focus="Defend what's on the resume.",
        )
    )

    for planned in plan.rounds:
        if planned.kind.upper() != "EXERCISE":
            continue
        if len(rounds) - 1 >= MAX_EXERCISE_ROUNDS:
            break
        entry = get_question(planned.question_id)
        if entry is None:
            # Hallucinated or stale id. Drop the round rather than guess a
            # replacement -- a wrong-but-plausible question is worse than
            # one fewer round.
            continue
        rounds.append(
            PlannedRound(
                kind="EXERCISE",
                question_id=entry["id"],
                # The catalogue's own timing wins over the model's.
                minutes=entry["minutes"],
                focus=planned.focus or "",
            )
        )

    return InterviewPlan(
        vertical=(plan.vertical or "unknown").strip().lower()[:40],
        rationale=plan.rationale.strip()[:500],
        rounds=rounds,
    )


def conversation_only_plan(reason: str = "planner unavailable") -> InterviewPlan:
    """The safe fallback: exactly the interview that ships today."""
    return InterviewPlan(
        vertical="unknown",
        rationale=reason,
        rounds=[
            PlannedRound(
                kind="CONVERSATION",
                question_id="",
                minutes=MAX_CONVERSATION_MINUTES,
                focus="Defend what's on the resume.",
            )
        ],
    )


def build_agenda_block(plan: InterviewPlan, current_round: int = 0) -> str:
    """
    The agenda, written for the INTERVIEWER to read.

    This exists because it was missing and the interviewer noticed: asked
    to move to a coding round, it replied "I have no coding round
    scheduled for you today" while two SQL exercises were in fact
    scheduled. It had a begin_round tool and no knowledge of whether there
    was anything to begin, so it improvised -- and improvising about the
    agenda means lying to the candidate.
    """
    lines = []
    for index, planned in enumerate(plan.rounds):
        marker = " <- you are here" if index == current_round else ""
        if planned.kind == "CONVERSATION":
            lines.append(f"{index + 1}. This conversation, about {planned.minutes} minutes{marker}")
            continue
        entry = get_question(planned.question_id)
        if entry is None:
            continue
        kind = {
            "CODE": "Coding exercise",
            "SQL": "SQL exercise",
            "MCQ": "Quick-fire questions",
            "WRITTEN": "Written answer",
        }.get(entry["format"], entry["format"])
        lines.append(
            f"{index + 1}. {kind}: \"{entry.get('title', planned.question_id)}\" "
            f"({planned.minutes} minutes){marker}"
        )

    remaining = len(plan.rounds) - current_round - 1
    if remaining > 0:
        closing = (
            "When you have covered enough ground here, call begin_round to move to the next item.\n"
            "If the candidate asks what is coming, or asks to move on to it, answer ACCURATELY "
            "from this list -- and if they are ready, just call begin_round."
        )
    else:
        closing = (
            "There is nothing scheduled after this. Do not promise the candidate an exercise, a "
            "coding round, or anything else that is not on this list. When you have covered enough "
            "ground, call end_interview."
        )

    return f"""

---
TODAY'S AGENDA -- this is the whole interview. Do not misstate it:

{chr(10).join(lines)}

{closing}

Note the FORMAT of each item. A SQL exercise is not a coding puzzle and a
coding puzzle is not a SQL exercise; describe what is actually scheduled.
"""


def plan_summary(plan: InterviewPlan) -> List[Dict[str, Any]]:
    """Agenda for the candidate -- shown before they join."""
    summary = []
    for planned in plan.rounds:
        if planned.kind == "CONVERSATION":
            summary.append({"label": "Conversation", "detail": "Defending your resume", "minutes": planned.minutes})
            continue
        entry = get_question(planned.question_id)
        if entry is None:
            continue
        label = {
            "CODE": "Coding",
            "SQL": "SQL",
            "MCQ": "Quick-fire questions",
            "WRITTEN": "Written answer",
        }.get(entry["format"], entry["format"])
        summary.append({"label": label, "detail": planned.focus, "minutes": planned.minutes})
    return summary


def find_round(plan: InterviewPlan, index: int) -> Optional[PlannedRound]:
    if 0 <= index < len(plan.rounds):
        return plan.rounds[index]
    return None
