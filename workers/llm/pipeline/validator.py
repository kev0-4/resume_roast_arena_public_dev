"""
workers/llm/pipeline/validator.py

Turns the raw structured Gemini response into a RoastResult: grounds
HIGHLIGHTS quotes against the real resume text, and attaches severity to
quality_flags (the model only ever returns codes -- see
workers/llm/schemas.py's QUALITY_SEVERITY for why).

HIGHLIGHTS is the one thing response_schema can't enforce -- JSON mode
guarantees *shape*, not that a quote is real. Every quote is checked
against the actual resume text the LLM was shown (the caller passes it in
as `source_text`), and any quote that isn't a real verbatim substring is
silently dropped rather than surfaced. This is the one thing standing
between "the LLM picked a real detail out of this specific resume" and
"the LLM made something up that sounds plausible" -- the latter is exactly
the AI-slop failure mode this exists to prevent, so it's enforced in code,
not just asked for in the prompt.
"""

import re
from typing import List

from ..schemas import LLMStructuredResponse, RoastResult, Highlight, QualityIssue, QUALITY_SEVERITY


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _ground_highlights(highlights: List[Highlight], source_text: str) -> List[Highlight]:
    """
    Drop any highlight whose quote isn't a verbatim (whitespace-normalized)
    substring of `source_text`.

    If `source_text` is empty, grounding is skipped and every highlight is
    kept -- lets callers (and tests) exercise this without needing to
    fabricate a matching source document every time.
    """
    if not source_text:
        return highlights

    normalized_source = _normalize_whitespace(source_text)
    grounded: List[Highlight] = []
    for h in highlights:
        if not h.quote.strip() or not h.comment.strip():
            continue
        if _normalize_whitespace(h.quote) in normalized_source:
            grounded.append(h)
    return grounded


def parse_roast_output(response: LLMStructuredResponse, source_text: str = "") -> RoastResult:
    """
    Turn the parsed Gemini response into a RoastResult.

    Args:
        response:    the already-schema-validated response from call_roast_llm.
        source_text: the resume text the LLM was actually shown (normally
                      the full prompt, which contains it verbatim) -- used
                      only to ground HIGHLIGHTS quotes. Optional: pass ""
                      to skip grounding (e.g. in tests that don't care).

    Raises:
        ValueError: if verdict/roast are blank or fixes has no items --
                    response_schema guarantees the fields exist and have
                    the right *type*, not that they're non-empty/meaningful.
    """
    if not response.verdict.strip():
        raise ValueError("LLM response has an empty verdict")
    if not response.roast.strip():
        raise ValueError("LLM response has an empty roast")
    if not response.fixes or not any(f.strip() for f in response.fixes):
        raise ValueError("LLM response 'fixes' contains no actionable items")

    highlights = _ground_highlights(response.highlights, source_text)

    quality_issues = [
        QualityIssue(code=code, severity=QUALITY_SEVERITY[code])
        for code in dict.fromkeys(response.quality_flags)  # de-dupe, keep order
    ]

    return RoastResult(
        verdict=response.verdict.strip(),
        roast=response.roast.strip(),
        fixes=[f.strip() for f in response.fixes if f.strip()],
        highlights=highlights,
        quality_issues=quality_issues,
    )
