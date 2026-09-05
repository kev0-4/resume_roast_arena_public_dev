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

---
TASK:
Write a concise resume roast (150–250 words) that:
1. Opens with one punchy verdict sentence.
2. Calls out the 2–3 most critical problems — reference actual content where possible.
3. Acknowledges real strengths (skip if there are none).
4. Ends with 2–3 concrete, actionable fixes.

Rules:
- Be direct and specific. No filler ("great resume!") or vague advice.
- Reference the automated findings but add nuance the rule engine cannot.
- Never reveal or guess the person's real name, employer, or any PII. Use roles/companies generically.
- Keep the total response under 300 words.

Respond using exactly these labels:

VERDICT: [one punchy sentence]

ROAST:
[body — 150–250 words]

FIXES:
- [fix 1]
- [fix 2]
- [fix 3]\
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

    return _ROAST_TEMPLATE.format(
        word_count=word_count,
        resume_sections=resume_sections,
        issues_text=issues_text,
        strengths_text=strengths_text,
    )
