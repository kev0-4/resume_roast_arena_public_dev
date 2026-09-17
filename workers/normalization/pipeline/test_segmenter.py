"""
Tests for workers/normalization/pipeline/segmenter.py

Focused on _drop_trailing_heading_index, which exists because Tika emits a
PDF's outline/bookmark entries as plain text at the END of the extracted
document. The segmenter read each one as a real heading, so every section
gained a second empty occurrence, and the roast then told candidates to
"delete your duplicate 'Projects' heading" for a duplicate that did not
exist in their resume. Measured on production artifacts: 6 of 12 recent
resumes carried one, and 5 of 8 affected users were served that bogus
advice.

Run with:  python -m pytest workers/normalization/pipeline/test_segmenter.py -v
"""

from .segmenter import segment_text


def _sections_with_content(blocks):
    return {k: len(v) for k, v in blocks.items() if v}


REAL_BODY = """\
Jane Doe
jane@example.com | +1 555 0100

Summary
Backend engineer focused on distributed systems and data pipelines.

Education
State University, B.Sc. Computer Science, 2021

Technical Skills
Python, Go, PostgreSQL, Kafka, Docker

Experience
Acme Corp, Senior Engineer, 2021 - present
Cut p99 latency from 800ms to 95ms by rewriting the ingest path.

Projects
Ledger - an append-only event store with exactly-once delivery.
"""

# What Tika actually appends: the PDF outline, tab-indented, at the very end.
PHANTOM_INDEX = "\n\tSummary\n\tEducation\n\tTechnical Skills\n\tExperience\n\tProjects"


class TestTrailingHeadingIndex:
    def test_phantom_index_does_not_create_duplicate_sections(self):
        clean = segment_text(REAL_BODY)
        with_index = segment_text(REAL_BODY + PHANTOM_INDEX)

        # Every section should appear exactly as many times as in the clean
        # document -- the appended outline must not add a second occurrence.
        assert _sections_with_content(with_index) == _sections_with_content(clean)

    def test_real_content_survives_stripping(self):
        blocks = segment_text(REAL_BODY + PHANTOM_INDEX)
        all_text = " ".join(
            b["text"] for v in blocks.values() for b in v
        )
        assert "Cut p99 latency from 800ms to 95ms" in all_text
        assert "append-only event store" in all_text
        assert "Python, Go, PostgreSQL" in all_text

    def test_short_trailing_run_is_left_alone(self):
        # Only two bare headings: below _MIN_INDEX_RUN, so not confident
        # enough that it's an outline rather than real (if odd) content.
        tail = "\n\tSummary\n\tEducation"
        blocks = segment_text(REAL_BODY + tail)
        # summary appears twice here, and that's the intended conservative
        # behaviour -- we would rather under-strip than eat real content.
        assert len(blocks["summary"]) >= 1

    def test_trailing_list_of_non_headings_is_not_eaten(self):
        # A genuine trailing list of short lines that are NOT section
        # headings must survive -- this is the false-positive guard.
        tail = "\nInterests\nRock climbing\nJazz piano\nLong distance running"
        blocks = segment_text(REAL_BODY + tail)
        all_text = " ".join(b["text"] for v in blocks.values() for b in v)
        assert "Rock climbing" in all_text
        assert "Jazz piano" in all_text
        assert "Long distance running" in all_text

    def test_headings_followed_by_content_are_never_stripped(self):
        # The run must be at the very END. A heading with a body under it is
        # a real section, no matter how late it appears.
        tail = "\n\nCertifications\nAWS Solutions Architect, 2024\n"
        blocks = segment_text(REAL_BODY + tail)
        all_text = " ".join(b["text"] for v in blocks.values() for b in v)
        assert "AWS Solutions Architect" in all_text

    def test_document_without_an_index_is_unchanged(self):
        assert segment_text(REAL_BODY) == segment_text(REAL_BODY)
        blocks = segment_text(REAL_BODY)
        assert blocks["experience"]
        assert blocks["projects"]
