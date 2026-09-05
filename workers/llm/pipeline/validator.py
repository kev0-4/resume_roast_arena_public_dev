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
"""

from typing import Dict, List
from ..schemas import RoastResult


_LABELS = ("VERDICT", "ROAST", "FIXES")


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


def parse_roast_output(text: str) -> RoastResult:
    """
    Parse the LLM response text into a structured RoastResult.

    Raises:
        ValueError: if required sections are missing or FIXES has no items.
    """
    sections = _split_sections(text)

    missing = [label for label in _LABELS if not sections.get(label)]
    if missing:
        raise ValueError(
            f"LLM output missing required section(s): {missing}. "
            f"Got sections: {list(sections.keys())}"
        )

    fixes = _parse_fixes(sections["FIXES"])
    if not fixes:
        raise ValueError("LLM output 'FIXES' section contains no actionable items")

    return RoastResult(
        verdict=sections["VERDICT"],
        roast=sections["ROAST"],
        fixes=fixes,
    )
