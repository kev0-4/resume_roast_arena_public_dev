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

A block opened by a heading that is nothing but a heading also carries an
optional "heading": str (that line, stripped). "text" still begins with it.
Blocks opened by a line that carries content ("Summary: Backend engineer...")
and the run of lines before the first heading have no "heading" key.

'''
import re
from typing import Dict, List, Optional
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
# The unqualified forms below match any line that STARTS with the word, which
# has always been loose. The qualified forms ("Professional Summary",
# "Relevant Experience") are deliberately stricter: they must be the WHOLE
# line, so an ordinary sentence that happens to begin "Professional experience
# in Python and Go" can never be promoted to a heading.
#
# Why they exist: "Professional Summary" and "Professional Experience" are two
# of the most common headings on real resumes, and neither matched. The
# experience case was expensive, not cosmetic -- with no experience section the
# rule engine raised NO_EXPERIENCE (critical) plus NO_DATES_IN_EXPERIENCE
# (high), together a -15 point structural cost, and the experience content was
# filed under whatever section came before it.
SECTION_PATTERNS = {
    "summary": re.compile(
        r"^(summary|profile|objective)\b"
        r"|^(professional|career|executive)\s+(summary|profile|objective)\s*:?\s*$",
        re.I),
    "experience": re.compile(
        r"^(experience|work experience|employment)\b"
        r"|^(professional|relevant)\s+(experience|work experience)\s*:?\s*$",
        re.I),
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
    # The heading line this buffer was opened with, or None when the buffer
    # started without one (the run of lines before the first heading).
    buffer_heading = None

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
                    heading=buffer_heading,
                )

            # Start new section and retain header text
            current_section = header
            buffer_lines = [line_text]
            buffer_heading = _heading_only(line_text)
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
            heading=buffer_heading,
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


def _heading_only(line_text: str) -> Optional[str]:
    """
    The stripped line if it is NOTHING BUT a heading, else None.

    This gates the block["heading"] field, and it has to be strict: a renderer
    deletes the recorded heading line so it isn't printed twice. A line like
    "Summary: Backend engineer, five years." is detected as a heading (it
    starts with the word) but it also CARRIES CONTENT, and recording it would
    make the renderer delete the candidate's actual summary. So only a line
    that is purely heading words qualifies -- a trailing colon is allowed
    ("Professional Summary:"), inline text after it is not.

    Anything not recorded simply keeps the old behaviour (the heading shows
    twice), which is a cosmetic quirk; a wrongly recorded one is data loss.
    """
    stripped = line_text.strip()
    core = stripped[:-1].rstrip() if stripped.endswith(":") else stripped
    return stripped if _HEADINGISH.match(core) else None


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
    heading: Optional[str] = None,
):
    # Lines already have \n endings from keepends=True, just concatenate
    text = "".join(buffer_lines)

    # Adjust span for any leading whitespace stripped
    lstripped = text.lstrip()
    leading = len(text) - len(lstripped)
    rstripped = lstripped.rstrip()

    if not rstripped:
        return

    block = {
        "text": rstripped,
        "source_span": {
            "start": start + leading,
            "end": end,
        },
    }
    # Which line of `text` is the heading that opened this block, kept as its
    # own field. `text` still begins with it (offsets, entity spans, metrics
    # and signals all depend on that), but a renderer that prints its own
    # section label above the block needs to know so it can avoid showing the
    # heading twice -- the model read the doubled word as a real duplicate and
    # told candidates to delete their own "Summary" heading. Only present when
    # the block was opened by a heading; blocks written before this field
    # existed simply lack it, and every consumer treats that as "unknown".
    if heading:
        block["heading"] = heading
    blocks[section].append(block)
    