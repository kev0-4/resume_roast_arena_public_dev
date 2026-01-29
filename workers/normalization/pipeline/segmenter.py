# LEFT TO IMPLEMENT , SKELETON DONE, TODOS GEN - COMPELTED AND TEST LEFT
'''
Docstring for workers.normalization.pipeline.segmenter
Take trusted raw_text (from loader)

Split it into ordered, deterministic sections

Return blocks ready for entity extraction & signals


expected output
{
  "summary": [ { "text": str, "source_span": { "start": int, "end": int } } ],
  "experience": [ { "text": str, "source_span": {...} } ],
  "education": [ ... ],
  "skills": [ ... ],
  "projects": [ ... ],
  "certifications": [ ... ],
  "other": [ ... ]
}

'''
import re
from typing import Dict, List

SECTION_ORDER = [
    "summary",
    "experience",
    "education",
    "skills",
    "projects",
    "certifications",
    "other",
]
SECTION_PATTERNS = {
    "summary": re.compile(r"^(summary|profile|objective)\b", re.I),
    "experience": re.compile(r"^(experience|work experience|employment)\b", re.I),
    "education": re.compile(r"^(education|academics)\b", re.I),
    "skills": re.compile(r"^(skills|technical skills|technologies)\b", re.I),
    "projects": re.compile(r"^(projects|academic projects)\b", re.I),
    "certifications": re.compile(r"^(certifications|certificates)\b", re.I),
}


def segment_text(raw_text: str) -> dict:
    # ------------------------------------------------------------
    # 1. Initialize output structure
    # ------------------------------------------------------------
    blocks: Dict[str, List[dict]] = {k: [] for k in SECTION_ORDER}

    # ------------------------------------------------------------
    # 2. Split text into lines with spans
    # ------------------------------------------------------------
    # TODO:
    # - Split on '\n'
    # - Track start/end character offsets per line
    # - Preserve original indices for source_span
    lines = _split_lines_with_spans(raw_text)

    # ------------------------------------------------------------
    # 3. Iterate lines, detect headers, accumulate content
    # ------------------------------------------------------------
    current_section = None
    buffer_lines = []
    buffer_start = None

    for line_text, start, end in lines:
        header = _detect_header(line_text)

        if header:
            # Flush previous buffer
            if buffer_lines:
                _flush_buffer(
                    blocks=blocks,
                    section=current_section or "other",
                    buffer_lines=buffer_lines,
                    start=buffer_start,
                    end=prev_end,
                )
                buffer_lines = []

            # Start new section
            current_section = header
            buffer_start = None
            continue

        # Accumulate content
        if not buffer_lines:
            buffer_start = start

        buffer_lines.append(line_text)
        prev_end = end

    # Flush tail buffer
    if buffer_lines:
        _flush_buffer(
            blocks=blocks,
            section=current_section or "other",
            buffer_lines=buffer_lines,
            start=buffer_start,
            end=prev_end,
        )

    # ------------------------------------------------------------
    # 4. Post-process blocks (trim empties)
    # ------------------------------------------------------------
    # TODO:
    # - Remove empty text blocks
    # - Strip whitespace
    # - Optionally merge very short blocks

    return blocks


# ----------------- Helper functions -----------------

def _split_lines_with_spans(text: str):
    """
    Yield tuples of (line_text, start_idx, end_idx).
    """
    # TODO:
    # - Iterate through text.splitlines(keepends=True)
    # - Track running index
    raise NotImplementedError


def _detect_header(line: str) -> str | None:
    """
    Return section name if line is a header, else None.
    """
    cleaned = line.strip().lower()
    if not cleaned or len(cleaned) > 50:
        return None

    for section, pattern in SECTION_PATTERNS.items():
        if pattern.match(cleaned):
            return section

    return None


def _flush_buffer(
    *,
    blocks: Dict[str, List[dict]],
    section: str,
    buffer_lines: List[str],
    start: int,
    end: int,
):
    """
    Append buffered text as a block to blocks[section].
    """
    text = "\n".join(buffer_lines).strip()
    if not text:
        return

    blocks[section].append(
        {
            "text": text,
            "source_span": {"start": start, "end": end},
        }
    )
