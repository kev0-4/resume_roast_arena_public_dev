"""
backend/src/interview/prompt_builder.py

Builds the mock-interviewer's prompts from the anonymized resume, the
existing roast, and the pasted job description.

Section-formatting helpers (normalize_placeholders, _format_resume_sections)
are duplicated from workers/scoring/pipeline/prompt_builder.py, not
imported -- backend/ and workers/ have no shared import boundary in this
codebase (see backend/src/routes/public.py's _compute_subscores docstring
for the same deliberate duplication, for the same reason: they're
separately deployable services with their own import roots).
"""

import re
from typing import Any, Dict, List

from .schemas import SCORE_MIN, SCORE_MAX

# ---------------------------------------------------------------------------
# Section formatting (duplicated from workers/scoring/pipeline/prompt_builder.py)
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z]+)_\d+\}\}")


def normalize_placeholders(text: str) -> str:
    """Convert {{EMAIL_1}} -> [EMAIL], {{PHONE_2}} -> [PHONE], etc."""
    return _PLACEHOLDER_RE.sub(lambda m: f"[{m.group(1)}]", text)


_SECTION_ORDER = [
    "summary",
    "experience",
    "projects",
    "education",
    "skills",
    "certifications",
    "other",
]

_SECTION_LABELS: Dict[str, str] = {
    "summary": "SUMMARY / OBJECTIVE",
    "experience": "WORK EXPERIENCE",
    "projects": "PROJECTS",
    "education": "EDUCATION",
    "skills": "SKILLS",
    "certifications": "CERTIFICATIONS",
    "other": "OTHER",
}


def _section_text(block_list: List[Dict]) -> str:
    parts = [
        normalize_placeholders(b.get("text", "").strip())
        for b in block_list
        if isinstance(b, dict) and b.get("text", "").strip()
    ]
    return "\n".join(parts)


def _format_resume_sections(blocks: Dict[str, List[Dict]]) -> str:
    parts: List[str] = []
    for section in _SECTION_ORDER:
        if section in blocks:
            text = _section_text(blocks[section])
            if text:
                label = _SECTION_LABELS.get(section, section.upper())
                parts.append(f"[{label}]\n{text}")
    for section, block_list in blocks.items():
        if section not in _SECTION_ORDER:
            text = _section_text(block_list)
            if text:
                parts.append(f"[{section.upper()}]\n{text}")
    return "\n\n".join(parts) if parts else "(no content extracted)"


# ---------------------------------------------------------------------------
# Voice
# ---------------------------------------------------------------------------

# Kept as its own constant, verbatim-comparable to the roast prompt's own
# persona line (workers/scoring/pipeline/prompt_builder.py's _ROAST_TEMPLATE
# opening) so the two personas can be eyeballed side-by-side and never
# silently drift into a different tone.
_VOICE_BLOCK = """\
You are a brutally honest mock interviewer -- sharp, specific, and \
actionable, the same voice as the resume roast this candidate already \
received. You are not cruel for its own sake: every hard question and \
every cutting reaction lands on something real and useful, not a cheap \
shot. You are conducting a real interview, not writing a review -- react \
briefly and sharply to what the candidate just said, grounded in the \
specifics of their actual answer, then ask exactly one focused follow-up \
question at a time.\
"""


def build_interview_system_context(anonymized: Dict[str, Any], roast: Dict[str, Any], job_description: str) -> str:
    """
    The static per-interview context block, built once at interview start
    and reused unchanged across every turn's prompt (each Gemini call is
    stateless/one-shot -- no server-side chat-session state -- so this gets
    re-sent as plain text with every call, not held in a session object).

    Pulls the existing roast's verdict/roast/fixes/highlights/quality_flags
    in explicitly, framed as "you already told this candidate what's
    wrong" -- this is what lets the interviewer ask pointed follow-ups
    instead of generic questions.

    Raises:
        ValueError: if anonymized is missing required structure (mirrors
                    workers/scoring/pipeline/prompt_builder.py's own check).
    """
    content = anonymized.get("content")
    if not isinstance(content, dict):
        raise ValueError("anonymized artifact missing 'content' dict")
    blocks = content.get("blocks", {})
    if not isinstance(blocks, dict):
        raise ValueError("anonymized artifact 'content.blocks' is not a dict")

    resume_sections = _format_resume_sections(blocks)

    fixes_text = "\n".join(f"- {f}" for f in roast.get("fixes", [])) or "None recorded."
    highlights_text = "\n".join(
        f'- "{h.get("quote", "")}" -- {h.get("comment", "")}' for h in roast.get("highlights", [])
    ) or "None recorded."
    quality_flags_text = ", ".join(roast.get("quality_flags", [])) or "None recorded."

    return f"""\
{_VOICE_BLOCK}

---
CANDIDATE'S RESUME ({len(resume_sections)} chars):

{resume_sections}

---
JOB DESCRIPTION THEY'RE INTERVIEWING FOR:

{job_description.strip()}

---
THE ROAST THIS CANDIDATE ALREADY RECEIVED ON THIS RESUME -- use this to \
ask pointed follow-ups instead of generic interview questions. If the \
roast already called out a vague or unproven claim, ask the candidate to \
defend or explain it specifically.

Verdict: {roast.get("verdict", "")}
Roast: {roast.get("roast", "")}
Suggested fixes:
{fixes_text}
Quoted weak spots:
{highlights_text}
Flagged issues: {quality_flags_text}
"""


def build_opening_prompt(system_context: str) -> str:
    return f"""\
{system_context}

---
TASK: This interview is just starting. Ask your opening question -- one \
sharp, specific question that gets straight at the weakest or vaguest \
part of this resume relative to the job description above, not a generic \
"tell me about yourself." Leave reaction_text empty (there's no answer \
yet to react to). Set is_final_turn to false.\
"""


def build_turn_prompt(system_context: str, transcript_so_far: List[Dict[str, Any]]) -> str:
    """
    transcript_so_far: list of turn dicts (see interview/service.py for the
    exact shape) -- only fully-answered turns' question/answer_transcript
    pairs are rendered; the current (unanswered) turn's question is the
    caller's responsibility to make clear separately (it's implicit: it's
    the most recent question_text in transcript_so_far).
    """
    history_lines = []
    for turn in transcript_so_far:
        history_lines.append(f"Q{turn['turn']}: {turn['question_text']}")
        if turn.get("answer_transcript"):
            history_lines.append(f"A{turn['turn']}: {turn['answer_transcript']}")
    history_text = "\n".join(history_lines) if history_lines else "(no prior turns)"

    return f"""\
{system_context}

---
CONVERSATION SO FAR:

{history_text}

---
TASK: Listen to the attached audio -- it's the candidate's spoken answer \
to the most recent question above. First, transcribe what they actually \
said into answer_transcript (a faithful transcription, not a summary). \
Then react briefly and sharply to that specific answer (reaction_text), \
grounded in what they actually said -- not a generic response. Then ask \
exactly one focused follow-up question (next_question) that digs into a \
gap, a vague claim, or something worth pressing on -- either from this \
answer or another weak spot in the resume/roast context not yet covered. \
Set is_final_turn to true only if you genuinely judge this interview has \
covered enough ground; otherwise false.\
"""


def build_scoring_prompt(system_context: str, transcript: List[Dict[str, Any]]) -> str:
    """
    A separate call/prompt from the per-turn one, over the FULL transcript,
    so scoring always reasons over the complete conversation rather than
    just the final exchange.
    """
    history_lines = []
    for turn in transcript:
        history_lines.append(f"Q{turn['turn']}: {turn['question_text']}")
        if turn.get("answer_transcript"):
            history_lines.append(f"A{turn['turn']}: {turn['answer_transcript']}")
        if turn.get("reaction_text"):
            history_lines.append(f"Interviewer reaction: {turn['reaction_text']}")
    history_text = "\n".join(history_lines) if history_lines else "(no turns recorded)"

    return f"""\
{system_context}

---
FULL INTERVIEW TRANSCRIPT:

{history_text}

---
TASK: The interview is over. Score this candidate's performance from \
{SCORE_MIN} to {SCORE_MAX} based on how well they defended and \
elaborated on their resume under real questioning -- specificity, \
honesty, depth, and how well their answers actually addressed the job \
description above. A candidate who gave vague, evasive, or unsupported \
answers scores low even if their resume looked fine on paper; a \
candidate who gave sharp, specific, credible answers scores high even if \
their resume was thin. List concrete strengths, concrete weaknesses, and \
concrete next steps -- each grounded in something they actually said in \
this transcript, not generic interview advice.\
"""
