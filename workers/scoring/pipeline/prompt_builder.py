"""
workers/scoring/pipeline/prompt_builder.py

Builds a structured LLM prompt from anonymized resume content + scoring results.

Design (Option A): consumes the anonymized dict already in memory in the scoring
processor — no extra blob read required.

Placeholder conversion: stored format {{EMAIL_1}} → LLM-facing [EMAIL].
Reason: double-brace syntax looks like a template variable to an LLM; bracket
notation clearly communicates redaction.
"""

import re
from typing import Dict, Any, List

from ..schemas import ScoringResult, Issue, Severity, Strength


# ---------------------------------------------------------------------------
# Placeholder normalisation
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z]+)_\d+\}\}")


def normalize_placeholders(text: str) -> str:
    """Convert {{EMAIL_1}} → [EMAIL], {{PHONE_2}} → [PHONE], etc."""
    return _PLACEHOLDER_RE.sub(lambda m: f"[{m.group(1)}]", text)


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


def _format_resume_sections(blocks: Dict[str, List[Dict]]) -> str:
    parts: List[str] = []

    for section in _SECTION_ORDER:
        if section in blocks:
            text = _section_text(blocks[section])
            if text:
                label = _SECTION_LABELS.get(section, section.upper())
                parts.append(f"[{label}]\n{text}")

    # Catch any sections not in the known order
    for section, block_list in blocks.items():
        if section not in _SECTION_ORDER:
            text = _section_text(block_list)
            if text:
                parts.append(f"[{section.upper()}]\n{text}")

    return "\n\n".join(parts) if parts else "(no content extracted)"


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
Write a concise resume roast (150–250 words) that:
1. Opens with one punchy verdict sentence.
2. Calls out the 2–3 most critical problems — reference actual content where possible.
3. Acknowledges real strengths (skip if there are none).
4. Ends with 2–3 concrete, actionable fixes.

Also pull out 2–4 HIGHLIGHTS: short phrases (5–15 words) copied EXACTLY,
character-for-character, from the RESUME CONTENT above, each paired with a
sharp one-sentence roast comment on why it's weak (or, rarely, genuinely
strong). Do NOT paraphrase, summarize, or invent a quote — every highlight
must be a real, verbatim substring of the resume content shown above,
including its exact original wording and punctuation. If the resume
doesn't have enough genuinely quotable material, return fewer highlights
rather than inventing one.

Also assess CONTENT QUALITY — not structure (the rule engine already
covers that), the actual writing. Return every one of these codes that
clearly applies, in `quality_flags`. Leave a code out if it's a close
call or doesn't clearly apply — these should differentiate a strong
resume from a mediocre one, so only flag what you're confident about:

- GENERIC_BULLETS: describes responsibilities/duties, not outcomes or
  substance. Two equally valid ways a bullet avoids this — a real metric,
  OR real technical specificity:
  Weak: "Responsible for managing team projects and deadlines."
  Not generic (metric): "Led a 4-engineer team to cut deploy time from
  45min to 6min by migrating a monolith to microservices."
  Not generic (no metric, still strong): "Rewrote the log-ingestion
  service's deserializer in Rust to eliminate GC pauses under sustained
  write load, replacing a Java implementation that periodically stalled
  the consumer thread." Naming the exact tool, the exact problem, and the
  exact outcome is real substance even without a percentage sign.
  Not generic (named system + specific sub-components, no metric): "Payments
  reconciliation service: built the ledger-matching engine, the retry
  logic for failed bank transfers, and the daily settlement report."
  Naming a real system plus several specific, distinct capabilities
  actually built is real substance too — this is not the same as "worked
  on the payments system," which names nothing concrete.
- NO_QUANTIFIED_IMPACT: the bullet gives no real evidence of impact or
  capability at all — not the same as "has no digits in it." A resume
  demonstrating strength through concrete technical specificity (exact
  frameworks/protocols/algorithms named) or verifiable pedigree (a
  selective company or research institution, named specifically) is
  giving real evidence too, just not a percentage. Reserve this flag for
  bullets that are vague on BOTH fronts — no metric AND no concrete
  specifics, just a duty description. Use the quantified-impact check
  above as one input, not the deciding factor: a bullet can have a digit
  and still say nothing ("led 3 meetings a week"), and a bullet can have
  zero digits and still be strong ("built a distributed data pipeline in
  Kafka and Flink handling billions of events").
- BUZZWORD_FILLER: leans on vague corporate-speak ("results-driven",
  "team player", "synergy", "self-starter") instead of specifics.
- WEAK_ACTION_LANGUAGE: passive voice or repetitive/weak verbs throughout
  ("was responsible for", "helped with", "worked on") instead of direct,
  strong ones ("built", "led", "cut", "shipped").
- SHALLOW_CONTENT: technically present but superficial — one-line
  descriptions with no real depth or substance.

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
