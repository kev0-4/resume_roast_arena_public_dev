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
from backend.src.utils.telemetry import emit_event

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

    # Materialised because _drop_trailing_heading_index has to look at the
    # tail, which a generator can't do.
    lines = list(_split_lines_with_spans(raw_text))
    lines = _drop_trailing_heading_index(lines)

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
            emit_event(
                "normalization.segmenter.empty_blocks_dropped",
                {"section": section, "dropped_count": dropped_count, "status": "INFO"},
            )
            total_dropped += dropped_count
    if total_dropped > 0:
        emit_event(
            "normalization.segmenter.empty_blocks_total",
            {"total_dropped": total_dropped, "status": "INFO"},
        )
    return blocks


# ---------------------------------- Helper functions

_HEADINGISH = re.compile(r"^[A-Za-z][A-Za-z&/\- ]{2,39}$")

# A heading index needs at least this many lines before we believe it, and at
# least this many of them must be headings we actually recognise. Two anchors
# stop a genuine trailing list (e.g. three short interests) being eaten.
_MIN_INDEX_RUN = 3
_MIN_KNOWN_HEADINGS = 2


def _is_bare_heading(line_text: str) -> bool:
    """A line that is ONLY a section heading -- no body, no punctuation."""
    stripped = line_text.strip()
    if not stripped or not _HEADINGISH.match(stripped):
        return False
    # "Summary: I build..." is a heading with content, not a bare heading.
    return not stripped.endswith((".", ":", ",", ";"))


def _drop_trailing_heading_index(lines):
    """
    Remove a trailing run of bare section headings with no content under them.

    Tika emits a PDF's outline/bookmark entries as plain text at the END of
    the extracted document, so a resume whose PDF has bookmarks arrives
    looking like:

        ...last real bullet...
            Summary
            Education
            Technical Skills
            Experience
            Projects

    Those are not something the candidate wrote -- they are navigation
    metadata. But the segmenter reads each one as a real heading, so every
    section gains a second, empty occurrence, and the roast then tells the
    candidate to "delete your duplicate 'Projects' heading" for a duplicate
    that does not exist in their document. Measured on production artifacts:
    6 of 12 recent resumes carried one of these phantom indexes.

    Deliberately conservative: only a run at the very END, only when it is at
    least _MIN_INDEX_RUN lines long, and only when at least
    _MIN_KNOWN_HEADINGS of them match SECTION_PATTERNS -- so a real trailing
    list of short items is left alone.
    """
    if not lines:
        return lines

    run_start = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        text = lines[i][0].strip()
        if not text:
            continue  # blank lines inside the run are fine
        if _is_bare_heading(text):
            run_start = i
        else:
            break

    run = [l for l in lines[run_start:] if l[0].strip()]
    if len(run) < _MIN_INDEX_RUN:
        return lines

    known = sum(
        1 for line_text, _, _ in run
        if any(p.match(line_text.strip()) for p in SECTION_PATTERNS.values())
    )
    if known < _MIN_KNOWN_HEADINGS:
        return lines

    emit_event(
        "normalization.trailing_heading_index_dropped",
        {"lines_dropped": len(run), "headings": [l[0].strip() for l in run], "status": "INFO"},
    )
    return lines[:run_start]


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
    # Lines already have \n endings from keepends=True, just concatenate
    text = "".join(buffer_lines)

    # Adjust span for any leading whitespace stripped
    lstripped = text.lstrip()
    leading = len(text) - len(lstripped)
    rstripped = lstripped.rstrip()

    if not rstripped:
        return

    blocks[section].append(
        {
            "text": rstripped,
            "source_span": {
                "start": start + leading,
                "end": end,
            },
        }
    )
    