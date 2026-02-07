# LEFT TO IMPLEMENT , TODO: for v2 add Header false-positive guard
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
    # output structure

    blocks: Dict[str, List[dict]] = {k: [] for k in SECTION_ORDER}

   # 2. Split text into lines with spans

    lines = _split_lines_with_spans(raw_text)

    # ------------------------------------------------------------
    # 3. Iterate lines, detect headers, accumulate content
    current_section = None
    buffer_lines = []
    buffer_start = None
    prev_end = None

    for line_text, start, end in lines:
        header = _detect_header(line_text)

        if header:
            # Flush previous section content
            if buffer_lines:
                _flush_buffer(
                    blocks=blocks,
                    section=current_section or "other",
                    buffer_lines=buffer_lines,
                    start=buffer_start,
                    end=prev_end if prev_end is not None else buffer_start,
                )

            # Start new section and retain header text
            current_section = header
            buffer_lines = [line_text]
            buffer_start = start
            prev_end = end
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
            end=prev_end if prev_end is not None else buffer_start,
        )

    # ------------------------------------------------------------
    # 4. Post-process blocks (trim empties)
    total_dropped = 0
    for section in blocks:
        original_count = len(blocks[section])
        blocks[section] = [
            _block for _block in blocks[section]
            if _block["text"].strip()
        ]
        dropped_count = original_count-len(blocks[section])
        if dropped_count > 0:
            # TODO: REPLACE BOTH OF THESE PRINT STATEMENT WITH EMIT EVENT LATER
            print(
                f"[SEGMENTER] Dropped {dropped_count} empty block(s) from '{section}'")
            total_dropped += dropped_count
    if total_dropped > 0:
        print(f"[SEGMENTER] Total empty blocks removed: {total_dropped}")
    return blocks


# ---------------------------------- Helper functions

def _split_lines_with_spans(text: str):
    """
    Yield tuples of (line_text, start_idx, end_idx).
    """
    cursor = 0
    lines = text.splitlines(keepends=True)

    for _line in lines:
        start = cursor
        end = cursor + len(_line)
        yield (_line, start, end)
        cursor = end


def _detect_header(line: str) -> str | None:
    """
    Return section name if line is a header, else None.\
    Needs to pass these 3 checks
    >Line is short
    >Line matches known vocabulary
    >Line does not look like a sentence
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
