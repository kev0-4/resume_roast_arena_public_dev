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

from .catalogue import get_question
from .schemas import SCORE_MIN, SCORE_MAX

# ---------------------------------------------------------------------------
# Section formatting (duplicated from workers/scoring/pipeline/prompt_builder.py)
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z]+)_(\d+)\}\}")


def normalize_placeholders(text: str) -> str:
    """
    Convert {{EMAIL_1}} -> [EMAIL_1], {{PHONE_2}} -> [PHONE_2], etc.

    The index is KEPT -- see the twin of this function in
    workers/scoring/pipeline/prompt_builder.py for why. Short version:
    collapsing every link to a bare [URL] made distinct values look like
    duplicates, and the model dutifully told candidates to delete them.

    This copy also feeds build_resume_display_text, so the candidate's own
    side pane shows [URL_1] / [URL_2] rather than two identical [URL]s.
    """
    return _PLACEHOLDER_RE.sub(lambda m: f"[{m.group(1)}_{m.group(2)}]", text)


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


def _block_start(block: Dict) -> int | None:
    """Character offset of this block in the ORIGINAL document, if recorded."""
    span = block.get("source_span")
    if isinstance(span, dict) and isinstance(span.get("start"), int):
        return span["start"]
    return None


# ---------------------------------------------------------------------------
# PDF link-target dump (duplicated from workers/scoring/pipeline/prompt_builder.py)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\[(?:EMAIL|PHONE|URL)_\d+\]")
_URLISH_TOKEN_RE = re.compile(r"\[(?:EMAIL|URL)_\d+\]")
_PHONE_TOKEN_RE = re.compile(r"\[PHONE_\d+\]")

# Enough lines to be a machine-generated list rather than someone's two links.
_MIN_LINK_DUMP_LINES = 3

# A run this close to the top of the resume is the contact header, not a link
# dump. Stacked contact lines ("[EMAIL_1]" / "[URL_1]" / "[URL_2]", one per
# line) look exactly like a short dump, and telling the model that the
# candidate's own contact details are invisible file metadata would be wrong.
# Measured in NON-BLANK lines of the rendered text, section labels included.
_HEADER_ZONE_LINES = 8

_LINK_DUMP_NOTE = (
    "[LINK TARGETS EXTRACTED FROM THE PDF FILE -- the destinations behind "
    "hyperlinks elsewhere in this resume. They are NOT visible text on the "
    "candidate's page: the candidate sees a linked word, not this list. Do "
    "not comment on them, count them, or tell the candidate to delete them.]"
)


def _is_link_only_line(line: str) -> bool:
    """
    A line holding link/email placeholders and nothing else meaningful.

    A line carrying a PHONE placeholder never qualifies: the hidden link list
    Tika writes holds URLs and mailto: targets, so a phone number means this is
    the candidate's real, visible contact block.
    """
    stripped = line.strip()
    if not stripped or _PHONE_TOKEN_RE.search(stripped):
        return False
    if not _URLISH_TOKEN_RE.search(stripped):
        return False
    return not re.search(r"[A-Za-z0-9]", _TOKEN_RE.sub("", stripped))


def _label_link_dumps(rendered: str) -> str:
    """
    Mark (never delete) every hyperlink list Tika appended to the extracted text.

    Tika writes a PDF's link targets as plain text at the END OF EACH PAGE,
    the same way it writes the bookmark outline (see
    workers/normalization/pipeline/segmenter.py). The candidate sees the word
    "GradeIT" on their resume; we see the raw URL in a list they cannot find.
    The model then gave advice about text that is not on the page.

    This used to look only at the very end of the document, which handled every
    single-page PDF and missed every multi-page one: on a 2-page resume the
    first page's list lands mid-document, slipped through, and the roast told
    the candidate to delete "[URL_1] through [URL_10]" in 3 of 16 runs. So it
    now labels every qualifying run wherever it sits, one note per run.

    A run qualifies when it is 3+ consecutive link-only lines (blank lines
    between them don't break it) AND either it is the very last thing in the
    document or it starts outside the contact-header zone at the top. That
    zone, and the PHONE exclusion in _is_link_only_line, exist because a real
    stacked contact block is the one thing a mid-document rule could wrongly
    swallow.

    Labels rather than removes, deliberately. A rule that deletes text has to
    be right every time or it eats a real "Links" section; mislabelling one
    only costs a little roast coverage.
    """
    lines = rendered.splitlines()
    nonblank = [i for i, line in enumerate(lines) if line.strip()]

    insert_before: List[int] = []
    pos = 0
    while pos < len(nonblank):
        if not _is_link_only_line(lines[nonblank[pos]]):
            pos += 1
            continue
        end = pos
        while end + 1 < len(nonblank) and _is_link_only_line(lines[nonblank[end + 1]]):
            end += 1
        if end - pos + 1 >= _MIN_LINK_DUMP_LINES:
            is_last_thing = end == len(nonblank) - 1
            in_header_zone = pos < _HEADER_ZONE_LINES
            if is_last_thing or not in_header_zone:
                insert_before.append(nonblank[pos])
        pos = end + 1

    if not insert_before:
        return rendered
    # bottom-up, so earlier indices stay valid as notes are inserted
    for idx in reversed(insert_before):
        lines.insert(idx, _LINK_DUMP_NOTE)
    return "\n".join(lines)


def _strip_own_heading(block: Dict, text: str) -> str:
    """
    Drop the block's opening heading line, because the caller prints a section
    label above it.

    The segmenter keeps a section's heading as the first line of its block text
    (offsets and downstream signals depend on that) and, since this field was
    added, also records it separately as block["heading"]. Rendering both the
    "[SUMMARY / OBJECTIVE]" label and the untouched text showed the model
    "Summary" twice, and it sometimes told the candidate to delete the
    "redundant" heading -- roughly 1 roast in 6.

    Only strips when the recorded heading really is the first line, so a block
    without the field (anything written before it existed) is left exactly as
    it was.
    """
    heading = block.get("heading")
    if not isinstance(heading, str) or not heading.strip():
        return text
    first, _, rest = text.partition("\n")
    if first.strip() == normalize_placeholders(heading.strip()):
        return rest.strip()
    return text


def _format_resume_sections(blocks: Dict[str, List[Dict]]) -> str:
    """
    Render the resume block-by-block in TRUE document order.

    Kept byte-for-byte equivalent to the roast worker's own copy in
    workers/scoring/pipeline/prompt_builder.py -- see that docstring for the
    full history. Short version: emitting a fixed canonical order told the
    model the contact header (which lands in the catch-all 'other' bucket at
    offset 0, the TOP of most resumes) was at the bottom, and sorting whole
    sections still mislocated the stray trailing fragments that also land in
    'other'. Only ADJACENT same-section blocks are merged, so a section that
    genuinely repeats renders twice.

    This matters twice over here: the interviewer reasons about the resume
    from this text, AND build_resume_display_text() below renders it straight
    into the candidate's own side pane during the live call -- so a wrong
    order was being shown to both sides of the interview.
    """
    positioned: List[tuple] = []
    unpositioned: List[tuple] = []

    for section, block_list in blocks.items():
        if not isinstance(block_list, list):
            continue
        for block in block_list:
            if not isinstance(block, dict):
                continue
            text = normalize_placeholders((block.get("text") or "").strip())
            if not text:
                continue
            # May leave "" for a section that is only its heading; kept so the
            # section still shows as present-but-empty.
            text = _strip_own_heading(block, text)
            start = _block_start(block)
            if start is None:
                rank = (
                    _SECTION_ORDER.index(section)
                    if section in _SECTION_ORDER
                    else len(_SECTION_ORDER)
                )
                unpositioned.append((rank, section, text))
            else:
                positioned.append((start, section, text))

    positioned.sort(key=lambda t: t[0])
    unpositioned.sort(key=lambda t: t[0])
    flat = [(s, t) for _, s, t in positioned] + [(s, t) for _, s, t in unpositioned]

    runs: List[tuple] = []
    for section, text in flat:
        if runs and runs[-1][0] == section:
            runs[-1][1].append(text)
        else:
            runs.append((section, [text]))

    parts = [
        f"[{_SECTION_LABELS.get(section, section.upper())}]\n" + "\n".join(texts)
        for section, texts in runs
    ]
    if not parts:
        return "(no content extracted)"
    return _label_link_dumps("\n\n".join(parts))


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


def build_live_system_instruction(system_context: str, minutes: int = 10) -> str:
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

---
COVER GROUND -- YOU HAVE ABOUT {minutes} MINUTES, NOT AN HOUR:

The most common way this interview fails is spending the whole time \
grinding one bullet point. Do not do that.

- Aim to cover FOUR OR FIVE distinct areas of their resume and the job \
description. Breadth is the point: you are testing whether the whole CV \
holds up, not auditing a single project.
- Press at most TWICE on any one point. If the second answer is still \
vague, say so bluntly, note it as a gap, and MOVE ON anyway -- "that's \
still hand-wavy, but let's move on" is a complete and acceptable ending \
to a thread. A third attempt at the same question teaches nobody anything.
- Keep a rough clock in your head. If you are several minutes in and \
still on the first topic, you are too deep -- change subject immediately.
- Prefer a new area of the resume over a deeper layer of the current one. \
If they have three roles and a projects section, all of them are fair \
game and none of them should swallow the whole interview.
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


def describe_conduct(
    *,
    seconds_taken: int = 0,
    pasted: bool = False,
    runs: int = 0,
    failed_runs: int = 0,
    hidden_passed: int | None = None,
    hidden_total: int | None = None,
) -> str:
    """
    How the answer was produced, as opposed to what it says.

    This exists because the signals were being recorded and then used by
    nothing. A paste flag written to the database and read by no prompt is
    not a feature -- it told nobody anything. Same for run history: the
    agreed design is to record it and let the interviewer press on it,
    rather than silently deduct points for testing, which would just teach
    candidates to stop testing.
    """
    lines = []

    if seconds_taken:
        minutes, seconds = divmod(seconds_taken, 60)
        clock = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
        lines.append(f"- They took {clock}.")

    if pasted:
        lines.append(
            "- They PASTED code in rather than typing it. That is not proof of anything on its own, "
            "but combined with the time taken it is worth knowing. Do not accuse them. Do make them "
            "explain a specific line or decision in their own words -- someone who wrote it can, "
            "and someone who did not will struggle."
        )

    if runs:
        if failed_runs == 0:
            lines.append(f"- They ran the tests {runs} time(s), passing every time.")
        else:
            lines.append(
                f"- They ran the tests {runs} time(s), {failed_runs} of which failed before they got it working. "
                "Iterating is normal and good; only press if the pattern looks like guessing rather than reasoning."
            )
    elif runs == 0 and seconds_taken:
        lines.append("- They never ran the tests before submitting.")

    if hidden_total:
        lines.append(
            f"- Against hidden tests they never saw: {hidden_passed}/{hidden_total} passed. "
            "They do not know this number. If they failed some, find out whether they understand why "
            "without telling them which case broke."
        )

    return "\n".join(lines)


def build_review_prompt(
    question: Dict[str, Any], submission: str, language: str | None = None, conduct: str = ""
) -> str:
    """
    Grades one exercise submission without executing it.

    The most important output is not the score, it is interviewer_notes --
    the specific weakness the interviewer should open the debrief on.
    Probing showed that feeding this into the live session turns "walk me
    through your solution" into "you claimed O(1) but you call
    list.remove, justify that", which is the entire point of the round.
    """
    extra = ""
    if question["format"] == "CODE" and language:
        extra = f"\nLanguage: {language}\n"
    if question["format"] == "SQL":
        tables = "\n".join(
            f"  {t['table']}({', '.join(t['columns'])})" for t in question.get("schema", [])
        )
        extra = f"\nSchema they were given:\n{tables}\n"

    return f"""\
You are grading one exercise from a mock interview. The submission was NOT \
executed -- judge it by reading it.

---
QUESTION ({question["format"]}, {question["difficulty"]}):

{question["prompt"]}
{extra}
---
GRADING RUBRIC -- this is what a strong and a weak answer look like:

{question["rubric"]}

---
THE CANDIDATE SUBMITTED:

{submission.strip() or "(nothing -- they submitted an empty answer)"}

{("---" + chr(10) + "HOW THEY PRODUCED IT -- context, not a verdict:" + chr(10) + chr(10) + conduct + chr(10)) if conduct else ""}
---
TASK:

Judge it honestly and specifically.

- `correct`: does it actually solve the stated problem? An empty or \
irrelevant submission is false.
- `complexity`: the real time complexity for CODE and SQL (say "n/a" for \
WRITTEN), regardless of what the candidate claimed.
- `strengths` and `problems`: concrete, grounded in what they actually \
wrote. Quote their own identifiers or phrases. No generic advice.
- `interviewer_notes`: the single sharpest thing to press them on out \
loud, phrased for an interviewer to act on. This is not shown to the \
candidate. If they overstated something, say exactly where.
- `score`: {SCORE_MIN} to {SCORE_MAX} for this exercise alone.\
"""


def build_debrief_addendum(
    utterances: List[Dict[str, Any]],
    question: Dict[str, Any],
    submission: str,
    review: Dict[str, Any] | None,
    conduct: str = "",
) -> str:
    """
    Appended to the live system instruction when voice returns after an
    exercise round.

    Two jobs. It carries the conversation across a socket the candidate
    never knew closed -- ephemeral tokens silently ignore session
    resumption handles, verified twice, so re-seeding is the only way the
    interviewer remembers anything. And it hands over the automated review
    so the interviewer opens on the real weakness rather than a warm-up.
    """
    history = "\n".join(
        f"{'INTERVIEWER' if u.get('speaker') == 'interviewer' else 'CANDIDATE'}: {(u.get('text') or '').strip()}"
        for u in utterances
        if (u.get("text") or "").strip()
    ) or "(nothing said yet)"

    review_block = ""
    if review:
        problems = "\n".join(f"  - {p}" for p in review.get("problems", [])) or "  - none noted"
        review_block = f"""\

An automated review of that submission found:
  correct: {review.get("correct")}
  complexity: {review.get("complexity")}
  problems:
{problems}

The sharpest thing to press on: {review.get("interviewer_notes", "")}
"""

    conduct_block = ""
    if conduct:
        conduct_block = f"""
HOW THEY PRODUCED IT -- context for you, never to be read out as an
accusation:

{conduct}
"""

    return f"""

---
THE CONVERSATION SO FAR -- you already had this exchange with the
candidate. Continue naturally. Do NOT reintroduce yourself, do NOT restart
the interview, and do NOT repeat a question you already asked.

{history}

---
THEY HAVE JUST FINISHED AN EXERCISE ROUND.

Question set ({question["format"]}): {question.get("prompt", "")}

Their submission:

{submission.strip() or "(they submitted nothing)"}
{review_block}{conduct_block}
---
TASK: Debrief the code. This is the part of the interview the exercise
exists for -- do not skip past it in one question and return to the
resume.

Open by going straight at the weakest part of the submission. Do not
praise it first and do not ask them to walk through it from the top --
you have read it. One short spoken question, and make it the one they
would least like to be asked.

Then actually discuss the solution, covering three or four of these
before you move on, one question at a time:

- the complexity they claimed versus what the code actually does;
- an edge case it does not handle, asked as a scenario rather than a
  hint ("what happens if the same key is inserted twice?" not "you forgot
  to handle re-insertion");
- the design choice they made and what the alternative would cost;
- what breaks first when the input gets very large.

Same rules as the rest of the interview: at most two presses on any one
of these, then move on. If a hidden test failed, probe the behaviour
around it WITHOUT naming the case or telling them a test failed -- find
out whether they can reason their way to it.
"""


_ROUND_LABELS = {
    "CODE": "Coding exercise",
    "SQL": "SQL exercise",
    "MCQ": "Quick-fire questions",
    "WRITTEN": "Written answer",
}


def _exercise_rounds_block(round_results: List[Dict[str, Any]] | None) -> str:
    """
    Puts the already-graded exercise rounds in front of the final scorer.

    This exists because they were not there, and the omission was
    expensive: one candidate scored 10/10 on a coding round and came out
    of scoring with a final 1, because the scorer was handed the
    conversation transcript and nothing else. The round was graded, stored
    and shown to the candidate, and then counted for nothing on the
    leaderboard -- which makes the whole exercise feature decorative.

    Conversation-only interviews produce NO block at all, deliberately.
    An HR or IB candidate the planner correctly gave no exercise must not
    be told "they sat no exercises" -- that reads as a gap and would cap a
    vertical for a decision the product made on their behalf.
    """
    exercises = [
        r for r in (round_results or [])
        if isinstance(r, dict) and r.get("kind") != "CONVERSATION" and r.get("question_id")
    ]
    if not exercises:
        return ""

    blocks = []
    for result in exercises:
        entry = get_question(result.get("question_id", "")) or {}
        fmt = result.get("format") or entry.get("format") or "Exercise"
        label = _ROUND_LABELS.get(fmt, fmt)
        title = entry.get("title") or result.get("question_id")
        review = result.get("review") or {}
        score = review.get("score")

        lines = [
            f'{label} -- "{title}": scored '
            f'{score if score is not None else "?"}/{SCORE_MAX}'
            + (f' in {result["language"]}' if result.get("language") else "")
            + "."
        ]

        cases = result.get("cases") or {}
        case_bits = []
        if cases.get("visible_total"):
            case_bits.append(
                f'{cases.get("visible_passed", 0)} of {cases["visible_total"]} visible tests passed'
            )
        if cases.get("hidden_total"):
            case_bits.append(
                f'{cases.get("hidden_passed", 0)} of {cases["hidden_total"]} HIDDEN tests passed'
            )
        if case_bits:
            lines.append("  Tests: " + ", ".join(case_bits) + ".")

        conduct = (result.get("conduct") or "").strip()
        if conduct:
            lines.append("  " + conduct.replace("\n", " "))

        for field, heading in (("strengths", "Good"), ("problems", "Wrong")):
            items = [str(i).strip() for i in (review.get(field) or []) if str(i).strip()]
            if items:
                lines.append(f"  {heading}: " + "; ".join(items[:4]))

        notes = (review.get("interviewer_notes") or "").strip()
        if notes:
            lines.append("  Grader's notes: " + notes.replace("\n", " "))

        blocks.append("\n".join(lines))

    # Stated as a share rather than arithmetic because the output is one
    # integer, not a weighted sum -- and because the conversation is still
    # what this product is for. Two exercises is most of the interview's
    # time, so it gets close to half.
    weight = (
        "The exercise is roughly a THIRD of this candidate's final score."
        if len(exercises) == 1
        else f"The {len(exercises)} exercises together are roughly HALF of this candidate's final score."
    )

    return f"""
---
EXERCISES THEY ACTUALLY SAT, ALREADY GRADED:

{chr(10).join(blocks)}

These scores are evidence and they MUST move the final score. {weight} \
The rest is the conversation below, which includes them being debriefed \
on this work -- how they defended it there matters as much as the grade.

A strong exercise score cannot be ignored. If you are about to give a \
final score far BELOW an exercise score of 8 or more, the conversation \
must contain something that genuinely justifies it -- admitted cheating, \
refusing to engage, or being unable to explain their own submission -- \
and you must name that reason plainly in weaknesses. "The conversation \
was weak" is not enough on its own.

Equally, a good conversation does not rescue a failed exercise. If they \
scored 3 or less, or failed hidden tests they could not reason their way \
to when asked, that is a real limit on the score however well they talk.
"""


def build_scoring_prompt(
    system_context: str,
    utterances: List[Dict[str, Any]],
    *,
    skipped_questions: int = 0,
    ended_early: Dict[str, Any] | None = None,
    round_results: List[Dict[str, Any]] | None = None,
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

    round_results is the server's own record of the exercise rounds, taken
    from the interview row rather than the client: the grades were decided
    here, against expected values and answer keys that never left this
    process, so unlike the transcript they are not client-assertable.
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

    exercise_block = _exercise_rounds_block(round_results)
    # The task line otherwise tells the scorer this is purely a resume
    # defence, which flatly contradicts the block above it.
    graded_on = (
        "based on how well they defended and elaborated on their resume "
        "under real questioning AND how they did on the graded exercises "
        "above, taken together"
        if exercise_block
        else "based on how well they defended and elaborated on their resume "
        "under real questioning"
    )

    return f"""\
{system_context}
{exercise_block}
---
FULL INTERVIEW TRANSCRIPT:

{history_text}
{conduct_block}
---
TASK: The interview is over. Score this candidate's performance from \
{SCORE_MIN} to {SCORE_MAX} {graded_on} -- specificity, \
honesty, depth, and how well their answers actually addressed the job \
description above. A candidate who gave vague, evasive, or unsupported \
answers scores low even if their resume looked fine on paper; a \
candidate who gave sharp, specific, credible answers scores high even if \
their resume was thin. List concrete strengths, concrete weaknesses, and \
concrete next steps -- each grounded in something they actually said in \
this transcript, not generic interview advice.\
"""
