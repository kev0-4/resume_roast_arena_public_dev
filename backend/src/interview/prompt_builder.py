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


def build_resume_display_text(anonymized: Dict[str, Any]) -> str:
    """
    The resume as the candidate sees it in the live room's side pane.

    Deliberately the SAME anonymized text the interviewer is working from,
    not the original upload -- partly so both sides are demonstrably
    reading one document, and partly because the original often no longer
    exists (raw uploads are deleted after RAW_UPLOAD_TTL_HOURS).

    The roast is deliberately NOT included: it names the exact weak spots
    the candidate is about to be challenged on, which would turn the
    interview into an open-book test.
    """
    content = anonymized.get("content")
    if not isinstance(content, dict):
        return ""
    blocks = content.get("blocks", {})
    if not isinstance(blocks, dict):
        return ""
    return _format_resume_sections(blocks)


def build_live_system_instruction(system_context: str) -> str:
    """
    The systemInstruction handed to the Live API session.

    build_interview_system_context above is shared verbatim with scoring so
    the two calls can never disagree about who this candidate is. What gets
    added here is everything specific to the fact that this output will be
    SPOKEN, in real time, to someone who can interrupt it -- direction that
    would be meaningless in the scoring call.

    The "speak first" instruction matters more than it looks: without it
    the model waits for the candidate, the candidate waits for the model,
    and the interview opens with both sides silent.
    """
    return f"""\
{system_context}

---
HOW THIS CONVERSATION WORKS:

You are speaking out loud, live, to the candidate right now. This is a \
voice conversation, not writing.

- Open the interview yourself, immediately, without waiting to be \
prompted. Introduce yourself in one short line, then go straight to your \
first question -- a sharp, specific one aimed at the weakest or vaguest \
part of their resume relative to the job description, never a generic \
"tell me about yourself."
- Speak in short conversational turns. A couple of sentences, then stop \
and let them answer. Never deliver a monologue or a list.
- Ask exactly one question at a time, then actually wait.
- React to what they genuinely just said, quoting their own words back at \
them where it lands. If an answer is vague, evasive, or unsupported, say \
so plainly and press again on the same point.
- Never read out headings, bullet points, or anything that only makes \
sense written down. Everything you say gets spoken aloud.
- The candidate can and will interrupt you. If they start talking, stop \
and listen.
- Stay in character as the interviewer for the whole session. Do not \
break to explain that you are an AI, and do not narrate what you are \
doing.

---
WHEN THE CANDIDATE CANNOT ANSWER:

Pressing hard is right. Refusing to ever move on is not -- a candidate \
stuck on one question learns nothing and the interview stalls.

So: if they say they don't know, or ask to move on, push back exactly \
ONCE. Ask why they can't answer, or offer a narrower version of the same \
question -- often they know more than they think. If they still decline, \
call the skip_question tool and go to your next question. Say something \
short and honest as you move -- "Noted, that one's a gap" -- and do not \
keep circling back to it.

Calling skip_question is recorded and counts against their final score, \
so do not call it just because an answer was weak. Only call it when they \
actually decline to answer.

---
ENDING THE INTERVIEW:

You have an end_interview tool and you are expected to use it.

Call it with category COMPLETE once you have genuinely covered enough \
ground -- you do not have to fill the clock.

If the candidate is wasting your time -- asking you off-topic questions, \
trying to get you to answer their questions, baiting you, or refusing to \
engage -- warn them once, plainly. If they do it again, say one closing \
line and then call end_interview with category TIME_WASTING. Do not \
threaten to end the interview without actually calling the tool: saying \
"we're done" while the session keeps running wastes their time and ours.\
"""


def build_scoring_prompt(
    system_context: str,
    utterances: List[Dict[str, Any]],
    *,
    skipped_questions: int = 0,
    ended_early: Dict[str, Any] | None = None,
) -> str:
    """
    Scores the finished live conversation.

    utterances: merged speaker-tagged turns, as produced by
    interview/service.py's merge_transcript_chunks -- [{"speaker": ...,
    "text": ...}], where speaker is "interviewer" or "candidate". This is
    the Live API's own transcription of what was actually said on both
    sides, not a separate speech-to-text pass.

    skipped_questions / ended_early come from the interviewer's own tool
    calls during the session, counted client-side. They are passed in
    rather than inferred from the transcript because "did they actually
    decline, or was the answer merely weak?" is exactly the judgement the
    scorer would get wrong, and the interviewer already made it live.
    """
    history_lines = []
    for utterance in utterances:
        label = "INTERVIEWER" if utterance.get("speaker") == "interviewer" else "CANDIDATE"
        text = (utterance.get("text") or "").strip()
        if text:
            history_lines.append(f"{label}: {text}")
    history_text = "\n".join(history_lines) if history_lines else "(nothing was said)"

    conduct_lines = []
    if skipped_questions == 1:
        conduct_lines.append(
            "- The candidate declined to answer 1 question and asked to move on, after being "
            "pushed on it. Treat that as a real gap: name it in weaknesses and let it pull the "
            "score down. One skip is a dent, not a disqualification."
        )
    elif skipped_questions > 1:
        conduct_lines.append(
            f"- The candidate declined to answer {skipped_questions} questions and asked to move "
            "on each time, after being pushed. This is a serious pattern, not a one-off: it "
            "should weigh heavily against the score and be named plainly in weaknesses."
        )
    if ended_early:
        category = (ended_early.get("category") or "").upper()
        reason = (ended_early.get("reason") or "").strip()
        if category == "TIME_WASTING":
            conduct_lines.append(
                f'- The interviewer ENDED this interview early for time-wasting: "{reason}" '
                "The candidate spent the session avoiding the questions rather than answering "
                "them. Score accordingly -- this is near the bottom of the range."
            )
        elif category == "CANDIDATE_DISENGAGED":
            conduct_lines.append(
                f'- The interviewer ended this interview early because the candidate stopped '
                f'engaging: "{reason}" Score what was actually said, and note the disengagement.'
            )
        else:
            conduct_lines.append(
                f'- The interviewer judged the interview complete and ended it: "{reason}" '
                "This is normal and is NOT itself a negative -- a short interview that covered "
                "the ground is fine."
            )

    conduct_block = (
        "\n---\nHOW THE CANDIDATE CONDUCTED THEMSELVES:\n\n" + "\n".join(conduct_lines) + "\n"
        if conduct_lines
        else ""
    )

    return f"""\
{system_context}

---
FULL INTERVIEW TRANSCRIPT:

{history_text}
{conduct_block}
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
