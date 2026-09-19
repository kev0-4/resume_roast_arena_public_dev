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


# ---------------------------------------------------------------------------
# Qualified headings: "Professional Summary", "Professional Experience"
# ---------------------------------------------------------------------------

class TestQualifiedHeadings:
    """
    "Professional Summary" and "Professional Experience" are two of the most
    common headings on real resumes, and neither was recognised. The experience
    case was expensive, not cosmetic: no experience section meant NO_EXPERIENCE
    (critical) plus NO_DATES_IN_EXPERIENCE (high) from the rule engine -- a
    -15 structural cost -- and the candidate's experience was filed under
    whichever section came before it.

    The qualified forms must be the WHOLE line. The unqualified forms have
    always matched any line that merely starts with the word, and widening that
    looseness is how an ordinary sentence gets promoted to a heading.
    """

    def test_professional_summary_is_a_summary(self):
        blocks = segment_text(
            "Jane Doe\njane@example.com\n\nProfessional Summary\n"
            "Backend engineer.\n\nEducation\nState University")
        assert blocks["summary"]
        assert "Backend engineer." in blocks["summary"][0]["text"]

    def test_professional_experience_is_experience(self):
        blocks = segment_text(
            "Jane Doe\n\nEducation\nState University\n\nProfessional Experience\n"
            "Acme, Engineer, 2021 - present\nBuilt the ingest path.\n\nSkills\nPython")
        assert blocks["experience"]
        assert "Built the ingest path." in blocks["experience"][0]["text"]
        # ...and NOT filed under the section that came before it
        assert all("Built the ingest path." not in b["text"] for b in blocks["education"])

    def test_the_other_qualified_forms(self):
        for heading, section in [("Relevant Experience", "experience"),
                                 ("Career Objective", "summary"),
                                 ("Executive Summary", "summary"),
                                 ("Career Summary", "summary"),
                                 ("Professional Profile", "summary")]:
            blocks = segment_text(f"Jane\n\n{heading}\nSome content here.\n\nEducation\nSU")
            assert blocks[section], f"{heading!r} should open a {section} section"

    def test_case_and_trailing_colon_do_not_matter(self):
        for heading in ("PROFESSIONAL SUMMARY", "professional summary", "Professional Summary:"):
            blocks = segment_text(f"Jane\n\n{heading}\nBackend engineer.\n\nEducation\nSU")
            assert blocks["summary"], heading

    def test_a_sentence_that_starts_the_same_way_is_not_a_heading(self):
        # The false positive the whole-line rule exists to prevent.
        blocks = segment_text(
            "Jane\n\nSummary\nBackend engineer.\n"
            "Professional experience in Python and Go\n"
            "Professional summary of my work follows here\n\nEducation\nSU")
        assert len(blocks["summary"]) == 1
        assert not blocks["experience"]
        assert "Professional experience in Python and Go" in blocks["summary"][0]["text"]

    def test_unrelated_qualifiers_do_not_become_experience(self):
        blocks = segment_text("Jane\n\nLeadership Experience\nCaptain of the chess club\n")
        assert not blocks["experience"]

    def test_unqualified_headings_behave_exactly_as_before(self):
        for heading, section in [("Experience", "experience"),
                                 ("Work Experience", "experience"),
                                 ("Summary", "summary"),
                                 ("Profile", "summary"),
                                 ("Objective", "summary"),
                                 ("Summary of qualifications", "summary")]:
            blocks = segment_text(f"Jane\n\n{heading}\nSome content here.\n")
            assert blocks[section], heading


# ---------------------------------------------------------------------------
# The heading kept on each block
# ---------------------------------------------------------------------------

class TestHeadingField:
    """
    The heading stays as the first line of a block's text -- entity spans,
    offsets, metrics and signals all depend on that -- and is ALSO recorded as
    block["heading"], so a renderer that prints its own section label can avoid
    showing the word twice. Additive: nothing reading `text` or `source_span`
    sees any difference.
    """

    DOC = "Jane Doe\n\nSummary\nBackend engineer.\n\nEducation\nState University"

    def test_a_block_opened_by_a_heading_records_it(self):
        blocks = segment_text(self.DOC)
        assert blocks["summary"][0]["heading"] == "Summary"
        assert blocks["education"][0]["heading"] == "Education"

    def test_text_still_begins_with_the_heading(self):
        blocks = segment_text(self.DOC)
        assert blocks["summary"][0]["text"].startswith("Summary")

    def test_source_span_is_unchanged_by_the_field(self):
        blocks = segment_text(self.DOC)
        assert blocks["summary"][0]["source_span"]["start"] == self.DOC.index("Summary")

    def test_the_run_of_lines_before_any_heading_has_no_heading(self):
        blocks = segment_text(self.DOC)
        assert "heading" not in blocks["other"][0]

    def test_the_recorded_heading_is_the_stripped_line(self):
        blocks = segment_text("Jane\n\n\tExperience  \nBuilt X in 2022.\n")
        assert blocks["experience"][0]["heading"] == "Experience"

    def test_qualified_heading_is_recorded_verbatim(self):
        blocks = segment_text("Jane\n\nProfessional Summary\nBackend engineer.\n")
        assert blocks["summary"][0]["heading"] == "Professional Summary"


class TestHeadingFieldNeverCoversContent:
    """
    The renderer deletes the recorded heading line so it isn't printed twice.
    That is only safe if the recorded line is NOTHING BUT a heading. A line
    like "Summary: Backend engineer, five years." starts with a heading word,
    so it opens a section, but it also carries the candidate's real content;
    recording it as a heading made the renderer silently delete their summary.
    """

    def test_a_heading_with_content_on_the_same_line_records_no_heading(self):
        blocks = segment_text("Jane\n\nSummary: Backend engineer, five years.\nBuilt APIs.\n")
        assert blocks["summary"], "still recognised as a summary section"
        assert "heading" not in blocks["summary"][0]
        assert "Backend engineer, five years." in blocks["summary"][0]["text"]

    def test_a_heading_with_a_trailing_colon_alone_is_recorded(self):
        blocks = segment_text("Jane\n\nProfessional Summary:\nBackend engineer.\n")
        assert blocks["summary"][0]["heading"] == "Professional Summary:"

    def test_an_over_long_or_punctuated_line_records_no_heading(self):
        blocks = segment_text("Jane\n\nExperience (2019 - present, full time)\nBuilt X.\n")
        assert blocks["experience"]
        assert "heading" not in blocks["experience"][0]
