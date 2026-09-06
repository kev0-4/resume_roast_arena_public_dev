"""
workers/llm/pipeline/validator.py

Parses and validates the LLM's raw text output.

Expected format from the prompt template:

    VERDICT: [one punchy sentence]

    ROAST:
    [body]

    FIXES:
    - [fix 1]
    - [fix 2]
    - [fix 3]

    HIGHLIGHTS:
    "[exact quoted phrase]" :: [comment]
    "[exact quoted phrase]" :: [comment]

HIGHLIGHTS is the one section that isn't just parsed -- it's *grounded*:
every quote is checked against the actual resume text the LLM was shown
(the caller passes it in as `source_text`), and any quote that isn't a
real verbatim substring is silently dropped rather than surfaced. This is
the one thing standing between "the LLM picked a real detail out of this
specific resume" and "the LLM made something up that sounds plausible" --
the latter is exactly the AI-slop failure mode this exists to prevent, so
it's enforced in code, not just asked for in the prompt.
"""

import re
from typing import Dict, List
from ..schemas import Highlight, RoastResult


_LABELS = ("VERDICT", "ROAST", "FIXES", "HIGHLIGHTS")

_HIGHLIGHT_LINE_RE = re.compile(r'^\s*"(.+?)"\s*::\s*(.+?)\s*$')


def _split_sections(text: str) -> Dict[str, str]:
    """Split LLM output into named sections."""
    sections: Dict[str, str] = {}
    current: str | None = None
    buf: List[str] = []

    for line in text.splitlines():
        matched = False
        for label in _LABELS:
            if line.startswith(f"{label}:"):
                if current is not None:
                    sections[current] = "\n".join(buf).strip()
                current = label
                rest = line[len(label) + 1:].strip()
                buf = [rest] if rest else []
                matched = True
                break
        if not matched and current is not None:
            buf.append(line)

    if current is not None:
        sections[current] = "\n".join(buf).strip()

    return sections


def _parse_fixes(fixes_text: str) -> List[str]:
    """Extract bullet-point fixes from the FIXES section."""
    fixes = []
    for line in fixes_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Remove leading -, *, •, numbered prefixes like "1."
        cleaned = stripped.lstrip("-•*0123456789. ").strip()
        if cleaned:
            fixes.append(cleaned)
    return fixes


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _parse_highlights(highlights_text: str, source_text: str) -> List[Highlight]:
    """
    Parse `"quote" :: comment` lines and drop any quote that isn't a
    verbatim (whitespace-normalized) substring of `source_text` -- the
    grounding check described in this module's docstring.

    If `source_text` is empty, grounding is skipped and every well-formed
    line is kept -- lets callers (and tests) exercise the parsing logic
    without needing to fabricate a matching source document every time.
    A malformed or entirely missing HIGHLIGHTS section just yields an
    empty list; it never raises, since highlights are a bonus layered on
    top of the required verdict/roast/fixes output, not a required one.
    """
    normalized_source = _normalize_whitespace(source_text) if source_text else ""
    highlights: List[Highlight] = []
    for line in highlights_text.splitlines():
        match = _HIGHLIGHT_LINE_RE.match(line)
        if not match:
            continue
        quote, comment = match.group(1).strip(), match.group(2).strip()
        if not quote or not comment:
            continue
        if normalized_source and _normalize_whitespace(quote) not in normalized_source:
            continue
        highlights.append(Highlight(quote=quote, comment=comment))
    return highlights


def parse_roast_output(text: str, source_text: str = "") -> RoastResult:
    """
    Parse the LLM response text into a structured RoastResult.

    Args:
        text:        the raw LLM response.
        source_text: the resume text the LLM was actually shown (normally
                      the full prompt, which contains it verbatim) -- used
                      only to ground HIGHLIGHTS quotes. Optional: pass ""
                      to skip grounding (e.g. in tests that don't care).

    Raises:
        ValueError: if VERDICT/ROAST/FIXES are missing or FIXES has no
                    items. HIGHLIGHTS is never a reason to raise -- see
                    _parse_highlights.
    """
    sections = _split_sections(text)

    required = ("VERDICT", "ROAST", "FIXES")
    missing = [label for label in required if not sections.get(label)]
    if missing:
        raise ValueError(
            f"LLM output missing required section(s): {missing}. "
            f"Got sections: {list(sections.keys())}"
        )

    fixes = _parse_fixes(sections["FIXES"])
    if not fixes:
        raise ValueError("LLM output 'FIXES' section contains no actionable items")

    highlights = _parse_highlights(sections.get("HIGHLIGHTS", ""), source_text)

    return RoastResult(
        verdict=sections["VERDICT"],
        roast=sections["ROAST"],
        fixes=fixes,
        highlights=highlights,
    )
