"""
workers/scoring/pipeline/prompt_builder.py

Builds a structured LLM prompt from anonymized resume content + scoring results.

Design (Option A): consumes the anonymized dict already in memory in the scoring
processor — no extra blob read required.

Placeholder conversion: stored format {{EMAIL_1}} → LLM-facing [EMAIL_1].
Reason: double-brace syntax looks like a template variable to an LLM; bracket
notation clearly communicates redaction. The INDEX is preserved -- it used to
be dropped, which made distinct values indistinguishable to the model.
"""

import re
from typing import Dict, Any, List

from ..schemas import ScoringResult, Issue, Severity, Strength


# ---------------------------------------------------------------------------
# Placeholder normalisation
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z]+)_(\d+)\}\}")


def normalize_placeholders(text: str) -> str:
    """
    Convert {{EMAIL_1}} → [EMAIL_1], {{PHONE_2}} → [PHONE_2], etc.

    The index is KEPT. It used to be discarded, which meant a resume whose
    PDF carries twelve distinct links reached the model as twelve identical
    [URL] tokens -- so the model told the candidate to "delete the duplicated
    URLs" for links that are all different. Same for a header reading
    [URL] | [URL], which is really GitHub and LinkedIn.

    Only the braces needed changing: {{...}} reads as a template variable to
    an LLM, brackets read as a redaction. The number never had to go with
    them, and dropping it threw away the one thing that says these are
    different values.
    """
    return _PLACEHOLDER_RE.sub(lambda m: f"[{m.group(1)}_{m.group(2)}]", text)


# ---------------------------------------------------------------------------
# Section formatting
# ---------------------------------------------------------------------------

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
    """Concatenate all blocks in a section into one string."""
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
# PDF link-target dump
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\[(?:EMAIL|PHONE|URL)_\d+\]")

# Enough lines to be a machine-generated list rather than someone's two links.
_MIN_LINK_DUMP_LINES = 3

_LINK_DUMP_NOTE = (
    "[LINK TARGETS EXTRACTED FROM THE PDF FILE -- the destinations behind "
    "hyperlinks elsewhere in this resume. They are NOT visible text on the "
    "candidate's page: the candidate sees a linked word, not this list. Do "
    "not comment on them, count them, or tell the candidate to delete them.]"
)


def _is_link_only_line(line: str) -> bool:
    """A line holding redaction placeholders and nothing else meaningful."""
    stripped = line.strip()
    if not stripped or not _TOKEN_RE.search(stripped):
        return False
    return not re.search(r"[A-Za-z0-9]", _TOKEN_RE.sub("", stripped))


def _label_trailing_link_dump(rendered: str) -> str:
    """
    Mark (never delete) the hyperlink list Tika appends to extracted text.

    Tika writes a PDF's link targets as plain text at the end of the
    document, the same way it writes the bookmark outline (see
    workers/normalization/pipeline/segmenter.py). The candidate sees the word
    "GradeIT" on their resume; we see the raw URL in a list they cannot find.
    The model then gave advice about text that is not on the page.

    This labels the run instead of removing it, deliberately. A rule that
    deletes text has to be right every time or it eats a real "Links"
    section, and the production corpus offers too few examples to validate
    one. Mislabelling a genuine links section only costs a little roast
    coverage; deleting it would destroy content.

    Measured: fires on exactly the 2 of 9 production documents that carry the
    dump (11 lines each), and on none of the other 7.
    """
    lines = rendered.splitlines()
    run_start = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        if not lines[i].strip():
            continue
        if _is_link_only_line(lines[i]):
            run_start = i
        else:
            break

    if len([l for l in lines[run_start:] if l.strip()]) < _MIN_LINK_DUMP_LINES:
        return rendered

    return "\n".join(lines[:run_start] + [_LINK_DUMP_NOTE] + lines[run_start:])


def _format_resume_sections(blocks: Dict[str, List[Dict]]) -> str:
    """
    Render the resume block-by-block in TRUE document order.

    Two bugs led here, in order:

    1. The original emitted a fixed canonical order (summary, experience,
       ... other) regardless of real layout. A candidate's contact header is
       not a recognised section, so it lands in the catch-all 'other' bucket
       at offset 0 -- the TOP of almost every resume -- and canonical order
       printed 'other' LAST. The model kept telling people their contact
       details were "stranded at the very bottom" when they were at the top.

    2. Sorting whole SECTIONS by their earliest offset fixed section order but
       not this: a section's blocks can be scattered through the document.
       'other' routinely holds the contact header at offset 0 AND stray
       trailing fragments near the end. Grouped under one header at
       min(start), the model was told all of it sat at the top, and kept
       misplacing the trailing fragments.

    So blocks are flattened, sorted by their own offset, and only ADJACENT
    blocks of the same section are merged into one labelled run. A section
    that genuinely appears twice in the document therefore renders twice --
    which is the truth, and is also what lets the model report a duplicated
    heading structurally instead of inferring it from repeated text.

    Blocks with no usable span fall back to the end, ordered by the old
    canonical rank, so a malformed artifact degrades instead of losing
    content.
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

    # Merge only CONSECUTIVE blocks of the same section.
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
    return _label_trailing_link_dump("\n\n".join(parts))


# ---------------------------------------------------------------------------
# Issue / strength formatting
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]


def _format_issues(issues: List[Issue]) -> str:
    if not issues:
        return "None detected."
    lines: List[str] = []
    for severity in _SEVERITY_ORDER:
        for issue in issues:
            if issue.severity == severity:
                lines.append(f"[{issue.severity.value.upper()}] {issue.message}")
    return "\n".join(lines)


def _format_strengths(strengths: List[Strength]) -> str:
    if not strengths:
        return "None detected."
    return "\n".join(f"+ {s.message}" for s in strengths)


# ---------------------------------------------------------------------------
# Quantified-impact grounding signal (cheap, deterministic, no LLM call)
# ---------------------------------------------------------------------------

# Not a scored Issue/Strength -- this exists purely to give the LLM's own
# NO_QUANTIFIED_IMPACT judgment (see workers/llm/schemas.py) a concrete
# number to react to instead of pure vibes, which should make that call
# more consistent resume-to-resume. A regex catching "contains a digit or
# %" is a decent proxy for "backs up a claim with a number" but isn't the
# same thing (e.g. "led 3 meetings a week" has a digit but isn't real
# impact) -- which is exactly why this is grounding context for a judgment
# call, not a rule-engine deduction on its own.
_QUANTIFIED_RE = re.compile(r"\d|%")


def _quantified_bullet_ratio(blocks: Dict[str, List[Dict]]) -> str:
    bullet_sections = ("experience", "projects")
    lines: List[str] = []
    for section in bullet_sections:
        for block in blocks.get(section, []):
            text = block.get("text", "")
            lines.extend(line for line in text.splitlines() if line.strip())

    if not lines:
        return "No experience/project bullets to check."

    quantified = sum(1 for line in lines if _QUANTIFIED_RE.search(line))
    return f"{quantified} of {len(lines)} experience/project lines contain a number or percentage."


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_ROAST_TEMPLATE = """\
You are a brutally honest career coach delivering a resume "roast" — sharp, specific, and actionable.

The resume below has been screened by an automated rule engine. Its findings follow the content.

---
RESUME CONTENT ({word_count} words):

{resume_sections}

---
AUTOMATED FINDINGS:

Issues:
{issues_text}

Strengths:
{strengths_text}

Quantified-impact check: {quantified_ratio}

---
TASK:
Write a concise resume roast (140–180 words) that:
1. Opens with one punchy verdict sentence.
2. Calls out the 2–3 most critical problems — reference actual content where possible.
3. Acknowledges real strengths (skip if there are none).
4. Ends with 2–3 concrete, actionable fixes.

Each fix must name the SPECIFIC thing in this resume that is wrong, not
give a general instruction. Point at the actual offending text: the exact
section heading, the exact bullet, the exact phrase, the exact date. A
reader should be able to find the problem in their own document from the
fix alone, without having to guess which part you meant.

  Bad (generic — the reader has to guess what you meant):
    "Consolidate the duplicated sections and standardize your layout."
    "Add more metrics to your projects."
    "Fix the inconsistent formatting."
  Good (names the specific thing, so there is nothing to interpret):
    "The 'Projects' heading appears twice — once above 'MovieFlix' and
     again above 'Open Source'. Delete the second one and merge the
     entries under the first."
    "'Built a recommendation engine' has no numbers — say how many
     users it served or how much it lifted engagement."
    "Your 'Lock Free Video Frame Pipeline' project is dated Jul 2026,
     which is after your latest job ended in 2024. Correct the year."

Never tell the reader to "consolidate", "standardize", "improve" or
"optimize" something without saying exactly which text you mean.

CRITICAL — you do NOT know where anything sits on the page. The sections
above are printed in a fixed normalized order, NOT the order they appear
in the candidate's real document, and [OTHER] is a catch-all bucket whose
contents may come from anywhere in the file. A section printed last here
is very often at the TOP of their actual resume.

So never make a claim about physical position. Do not say something is
"at the top", "at the bottom", "at the very end", "above" or "below"
something else, do not say a section is "stranded", "buried" or
"misplaced", and never tell the reader to MOVE or REORDER anything.
Judge only what the text says, not where it appears.

This applies to the text shown above too, not just their document. Do not
describe where anything sits "in the text", "in the section", or relative
to anything else. If you catch yourself writing where something is rather
than what is wrong with it, delete that part of the sentence.

  Forbidden (position is unknowable from this prompt):
    "Move your contact info from the bottom up to the top."
    "Your summary is stranded at the very end — move it up."
    "Delete the duplicate 'Projects' heading near the bottom."
    "Your contact info is sitting at the very end of the text."
    "Delete the trailing 'Summary' heading at the bottom of the section."
  Allowed (identifies by content and name, no position):
    "Your 'Projects' heading appears more than once — keep one and merge
     the entries under it."
    "'Built a recommendation engine' has no numbers — say how many users
     it served."
    "Your contact details are split across multiple fragments — put name,
     phone, email and links together in one block."

Moving an ENTRY between sections is fine when the reason is categorical
("this is work experience, not a project") — that is about what something
is, not where it physically sits.

Also pull out 2–4 HIGHLIGHTS: short phrases (5–15 words) copied EXACTLY,
character-for-character, from the RESUME CONTENT above, each paired with a
sharp one-sentence roast comment on why it's weak (or, rarely, genuinely
strong). Do NOT paraphrase, summarize, or invent a quote — every highlight
must be a real, verbatim substring of the resume content shown above,
including its exact original wording and punctuation. If the resume
doesn't have enough genuinely quotable material, return fewer highlights
rather than inventing one.

Also judge CONTENT SUBSTANCE and return `substance_score` (0-100) with a
one-sentence `substance_reasoning`. This is the score the user sees, so
judge it carefully.

Substance means: does this resume give real evidence that this person did
meaningful work? There are several equally valid ways to show that, and a
resume needs only some of them. These apply the same way in every field —
an engineering resume dense with systems detail and a finance, research,
or operations resume dense with methodology and analytical rigor are
equally strong when each shows real depth in its own vocabulary:
- Quantified outcomes ("cut p99 latency from 800ms to 95ms", "structured
  a $400M leveraged buyout across three debt tranches")
- Concrete technical or methodological specificity (exact systems,
  protocols, algorithms, architectures, financial models, experimental
  designs, or legal/analytical frameworks named — "implemented an async
  AMQP client with a layered architecture", "built DCF and LBO models
  across six leverage scenarios to stress-test a bid")
- Verifiable pedigree (selective companies, research labs, published
  work, competitive fund or deal mandates)
- Scope and ownership (built a system end-to-end, led a team, owned a
  domain, drove an analysis or workstream that directly informed a real
  decision — a deal, a launch, a trade, a hire)

Rubric:
- 90-100: Clear, specific evidence of real, non-trivial work. Someone
  reading this learns what the person actually did and can judge its
  difficulty.
- 70-89: Real work is visible but under-sold — vague in places, or impact
  is implied rather than shown, or the hard parts aren't distinguished
  from the routine parts.
- 50-69: Mostly duty descriptions. You can tell what team they sat on,
  not what they contributed or how hard it was.
- 0-49: Content-free. Buzzwords, responsibilities, no evidence of
  anything specific.

Judge the WORK, not the writing polish, and not the field. A financial
analyst's sensitivity analysis across six scenarios to stress-test a
valuation is exactly as substantive as an engineer's cache-hit-rate
optimization — both show a specific method applied with judgment to a
real problem. Do not discount a deal's dollar value, a fund's size, or a
client-facing outcome as weaker evidence just because the number reflects
the deal's scale rather than lines of code — the rigor to look for is in
the method (which models, how many scenarios, what analysis actually
drove the recommendation), not in whether the artifact is software. A
terse resume describing genuinely hard work — technical or otherwise —
scores high. A polished resume full of numbers attached to routine tasks
does not — "improved efficiency by 8%" on an unremarkable task, or a
large deal size with no description of what analysis was actually done,
is not strong evidence on its own. Do not reward the mere presence of
digits or dollar signs.

Separately, return `quality_flags` — every code below that clearly
applies. These do NOT affect the score; they tell the user what to fix,
so include them wherever they're genuinely true even if the resume still
scores well overall:
- GENERIC_BULLETS: describes responsibilities/duties rather than what was
  actually built or achieved.
- NO_QUANTIFIED_IMPACT: no numbers, %, or scale anywhere the work's size
  or effect could have been shown.
- BUZZWORD_FILLER: leans on vague corporate-speak ("results-driven",
  "team player", "synergy", "self-starter") instead of specifics.
- WEAK_ACTION_LANGUAGE: passive voice or repetitive/weak verbs throughout
  ("was responsible for", "helped with", "worked on") instead of direct,
  strong ones ("built", "led", "cut", "shipped").
- SHALLOW_CONTENT: technically present but superficial — one-line
  descriptions with no real depth.

Rules:
- Be direct and specific. No filler ("great resume!") or vague advice.
- Reference the automated findings but add nuance the rule engine cannot.
- Never reveal or guess the person's real name, employer, or any PII. Use roles/companies generically.
- Every HIGHLIGHTS quote must be copied exactly from the RESUME CONTENT above — a quote that isn't a verbatim substring will be discarded entirely, so copy carefully rather than reconstructing from memory.
- Keep the total response under 350 words.\
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_roast_prompt(
    *,
    anonymized: Dict[str, Any],
    scoring_result: ScoringResult,
) -> str:
    """
    Build a structured LLM prompt from an in-memory anonymized artifact and
    the scoring result computed from it.

    Args:
        anonymized:     The full anonymized dict loaded by the scoring processor.
                        Must contain content.blocks, metrics.
        scoring_result: The ScoringResult produced by scorer.py.

    Returns:
        A formatted prompt string ready to pass to the LLM roast generator.

    Raises:
        ValueError: if anonymized is missing required structure.
    """
    content = anonymized.get("content")
    if not isinstance(content, dict):
        raise ValueError("anonymized artifact missing 'content' dict")

    blocks = content.get("blocks", {})
    if not isinstance(blocks, dict):
        raise ValueError("anonymized artifact 'content.blocks' is not a dict")

    metrics = anonymized.get("metrics", {})
    word_count = metrics.get("word_count", "unknown")

    resume_sections = _format_resume_sections(blocks)
    issues_text = _format_issues(scoring_result.issues)
    strengths_text = _format_strengths(scoring_result.strengths)
    quantified_ratio = _quantified_bullet_ratio(blocks)

    return _ROAST_TEMPLATE.format(
        word_count=word_count,
        resume_sections=resume_sections,
        issues_text=issues_text,
        strengths_text=strengths_text,
        quantified_ratio=quantified_ratio,
    )
