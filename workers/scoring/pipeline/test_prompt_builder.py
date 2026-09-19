"""
Unit tests for workers/scoring/pipeline/prompt_builder.py

Run with:  python -m pytest workers/scoring/pipeline/test_prompt_builder.py -v
"""

import pytest
from .prompt_builder import (
    normalize_placeholders,
    build_roast_prompt,
    _format_issues,
    _format_strengths,
    _format_resume_sections,
    _section_text,
    _label_link_dumps,
    _strip_own_heading,
    _LINK_DUMP_NOTE,
)
from ..schemas import ScoringResult, Issue, Strength, Severity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_block(text: str, start: int = 0, end: int = None) -> dict:
    end = end or start + len(text)
    return {"text": text, "source_span": {"start": start, "end": end}}


def _make_anonymized(blocks: dict, metrics: dict = None) -> dict:
    return {
        "session_id": "test-session",
        "anonymization_version": "1.0",
        "content": {"blocks": blocks},
        "redactions": {"emails": [], "phones": [], "urls": []},
        "signals": {},
        "metrics": metrics or {"word_count": 250},
        "timestamps": {
            "normalized_at": "2024-01-01T00:00:00",
            "anonymized_at": "2024-01-01T00:01:00",
        },
    }


def _make_scoring_result(issues=None, strengths=None) -> ScoringResult:
    return ScoringResult(
        issues=issues or [],
        strengths=strengths or [],
    )


# ---------------------------------------------------------------------------
# normalize_placeholders
# ---------------------------------------------------------------------------

class TestNormalizePlaceholders:
    def test_single_email(self):
        assert normalize_placeholders("reach me at {{EMAIL_1}}") == "reach me at [EMAIL_1]"

    def test_single_phone(self):
        assert normalize_placeholders("call {{PHONE_1}}") == "call [PHONE_1]"

    def test_single_url(self):
        assert normalize_placeholders("see {{URL_1}}") == "see [URL_1]"

    def test_multiple_same_type(self):
        result = normalize_placeholders("{{EMAIL_1}} and {{EMAIL_2}}")
        assert result == "[EMAIL_1] and [EMAIL_2]"

    def test_multiple_different_types(self):
        result = normalize_placeholders("{{EMAIL_1}} / {{PHONE_1}} / {{URL_1}}")
        assert result == "[EMAIL_1] / [PHONE_1] / [URL_1]"

    def test_no_placeholders(self):
        text = "No placeholders here, just plain text."
        assert normalize_placeholders(text) == text

    def test_empty_string(self):
        assert normalize_placeholders("") == ""

    def test_preserves_surrounding_text(self):
        result = normalize_placeholders("Email: {{EMAIL_1}}. Phone: {{PHONE_1}}.")
        assert result == "Email: [EMAIL_1]. Phone: [PHONE_1]."

    def test_high_numbered_placeholder(self):
        assert normalize_placeholders("{{URL_99}}") == "[URL_99]"

    def test_distinct_values_never_collapse_to_identical_tokens(self):
        """
        The regression this function used to cause.

        Tika appends a PDF's hyperlink list to the extracted text, so a
        resume can carry a dozen DISTINCT links. Discarding the placeholder
        index turned them into a dozen identical [URL] tokens, and the model
        -- correctly reading what it was given -- told the candidate to
        delete their "duplicated URLs". They were all different.
        """
        text = normalize_placeholders(
            "{{URL_1}}\n{{URL_2}}\n{{URL_3}}\n{{URL_4}}")
        tokens = text.split()
        assert len(set(tokens)) == len(tokens), (
            f"distinct links collapsed into duplicates: {tokens}")

    def test_contact_header_links_stay_distinguishable(self):
        # GitHub and LinkedIn in one header must not read as the same link.
        result = normalize_placeholders("{{URL_1}} | {{URL_2}}")
        assert result == "[URL_1] | [URL_2]"


# ---------------------------------------------------------------------------
# _section_text
# ---------------------------------------------------------------------------

class TestSectionText:
    def test_single_block(self):
        blocks = [_make_block("Software engineer with 5 years experience.")]
        assert _section_text(blocks) == "Software engineer with 5 years experience."

    def test_multiple_blocks_joined(self):
        blocks = [_make_block("Line one."), _make_block("Line two.")]
        result = _section_text(blocks)
        assert "Line one." in result
        assert "Line two." in result

    def test_placeholder_normalized(self):
        blocks = [_make_block("Contact: {{EMAIL_1}}")]
        assert _section_text(blocks) == "Contact: [EMAIL_1]"

    def test_empty_block_list(self):
        assert _section_text([]) == ""

    def test_blocks_with_empty_text_skipped(self):
        blocks = [_make_block(""), _make_block("   "), _make_block("Real content.")]
        assert _section_text(blocks) == "Real content."

    def test_non_dict_blocks_skipped(self):
        blocks = [None, "bad", _make_block("Good block.")]
        assert _section_text(blocks) == "Good block."


# ---------------------------------------------------------------------------
# _format_resume_sections
# ---------------------------------------------------------------------------

class TestFormatResumeSections:
    def test_known_sections_appear_with_labels(self):
        blocks = {
            "experience": [_make_block("Engineer at Acme.")],
            "education": [_make_block("B.Sc. Computer Science.")],
        }
        result = _format_resume_sections(blocks)
        assert "[WORK EXPERIENCE]" in result
        assert "[EDUCATION]" in result
        assert "Engineer at Acme." in result

    def test_section_order_respected(self):
        # source_span now drives order, so give them spans matching the
        # canonical layout this test was originally written against.
        blocks = {
            "education": [_make_block("B.Sc.", start=200)],
            "summary": [_make_block("Driven developer.", start=0)],
            "experience": [_make_block("3 years.", start=100)],
        }
        result = _format_resume_sections(blocks)
        # summary should appear before experience, experience before education
        assert result.index("[SUMMARY") < result.index("[WORK EXPERIENCE]")
        assert result.index("[WORK EXPERIENCE]") < result.index("[EDUCATION]")

    def test_sections_render_in_true_document_order_not_canonical(self):
        # The bug this guards: a user's contact header lands in the catch-all
        # 'other' bucket at offset 0 -- the TOP of their resume -- but the old
        # canonical order printed 'other' LAST. The model then told people
        # their contact details were "stranded at the very bottom" when they
        # were already at the top. Measured across 12 consecutive production
        # roasts: 11 were shown in the wrong order, 9 gave false positional
        # advice off the back of it.
        blocks = {
            "experience": [_make_block("Engineer at Acme.", start=500)],
            "other": [_make_block("Jane Doe | [EMAIL_1] | [PHONE_1]", start=0)],
            "education": [_make_block("B.Sc.", start=900)],
        }
        result = _format_resume_sections(blocks)
        assert result.index("[OTHER]") < result.index("[WORK EXPERIENCE]"), (
            "contact block at offset 0 must render first, not last"
        )
        assert result.index("[WORK EXPERIENCE]") < result.index("[EDUCATION]")

    def test_sections_without_spans_fall_back_instead_of_disappearing(self):
        # A malformed artifact should degrade to the old canonical behaviour,
        # never silently drop content out of the prompt.
        blocks = {
            "skills": [{"text": "Python, Go"}],            # no source_span
            "summary": [_make_block("Real summary.", start=10)],
        }
        result = _format_resume_sections(blocks)
        assert "[SKILLS]" in result
        assert "Python, Go" in result
        # positioned content wins the earlier slot
        assert result.index("[SUMMARY") < result.index("[SKILLS]")

    def test_prompt_forbids_positional_claims(self):
        # Position is unknowable to the model for any section lacking spans,
        # and [OTHER] is a catch-all that can hold content from anywhere, so
        # the prompt must not invite "move this to the top" style advice.
        anonymized = _make_anonymized(blocks={})
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "never make a claim about physical position" in prompt.lower()
        assert "stranded" in prompt

    def test_unknown_section_appended(self):
        blocks = {
            "awards": [_make_block("Best Employee 2023.")],
        }
        result = _format_resume_sections(blocks)
        assert "[AWARDS]" in result
        assert "Best Employee 2023." in result

    def test_empty_blocks_dict(self):
        result = _format_resume_sections({})
        assert "(no content extracted)" in result

    def test_sections_with_empty_text_omitted(self):
        blocks = {
            "summary": [_make_block("")],
            "experience": [_make_block("Real work.")],
        }
        result = _format_resume_sections(blocks)
        assert "[SUMMARY" not in result
        assert "[WORK EXPERIENCE]" in result


# ---------------------------------------------------------------------------
# _format_issues
# ---------------------------------------------------------------------------

class TestFormatIssues:
    def test_empty_issues(self):
        assert _format_issues([]) == "None detected."

    def test_critical_first(self):
        issues = [
            Issue(code="A", message="Low severity", severity=Severity.LOW),
            Issue(code="B", message="Critical problem", severity=Severity.CRITICAL),
        ]
        result = _format_issues(issues)
        assert result.index("[CRITICAL]") < result.index("[LOW]")

    def test_severity_order_full(self):
        issues = [
            Issue(code="D", message="Low", severity=Severity.LOW),
            Issue(code="C", message="Medium", severity=Severity.MEDIUM),
            Issue(code="B", message="High", severity=Severity.HIGH),
            Issue(code="A", message="Critical", severity=Severity.CRITICAL),
        ]
        result = _format_issues(issues)
        assert result.index("[CRITICAL]") < result.index("[HIGH]")
        assert result.index("[HIGH]") < result.index("[MEDIUM]")
        assert result.index("[MEDIUM]") < result.index("[LOW]")

    def test_issue_message_present(self):
        issues = [Issue(code="X", message="Missing summary section", severity=Severity.LOW)]
        assert "Missing summary section" in _format_issues(issues)


# ---------------------------------------------------------------------------
# _format_strengths
# ---------------------------------------------------------------------------

class TestFormatStrengths:
    def test_empty_strengths(self):
        assert _format_strengths([]) == "None detected."

    def test_strength_message_present(self):
        strengths = [Strength(code="S1", message="Good vocabulary diversity")]
        assert "Good vocabulary diversity" in _format_strengths(strengths)

    def test_multiple_strengths(self):
        strengths = [
            Strength(code="S1", message="Has experience section"),
            Strength(code="S2", message="Includes project experience"),
        ]
        result = _format_strengths(strengths)
        assert "Has experience section" in result
        assert "Includes project experience" in result


# ---------------------------------------------------------------------------
# build_roast_prompt (integration)
# ---------------------------------------------------------------------------

class TestBuildRoastPrompt:
    def test_returns_string(self):
        anonymized = _make_anonymized(
            blocks={"experience": [_make_block("Engineer at Acme.")]}
        )
        result = _make_scoring_result()
        prompt = build_roast_prompt(anonymized=anonymized, scoring_result=result)
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_prompt_contains_resume_content(self):
        anonymized = _make_anonymized(
            blocks={"experience": [_make_block("Senior engineer at BigCorp.")]}
        )
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "Senior engineer at BigCorp." in prompt

    def test_placeholders_converted_in_prompt(self):
        anonymized = _make_anonymized(
            blocks={"experience": [_make_block("Email: {{EMAIL_1}}")]}
        )
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "{{EMAIL_1}}" not in prompt
        assert "[EMAIL_1]" in prompt

    def test_issues_appear_in_prompt(self):
        anonymized = _make_anonymized(blocks={})
        scoring_result = _make_scoring_result(
            issues=[Issue(code="NO_SUMMARY", message="Missing summary section", severity=Severity.LOW)]
        )
        prompt = build_roast_prompt(anonymized=anonymized, scoring_result=scoring_result)
        assert "Missing summary section" in prompt

    def test_strengths_appear_in_prompt(self):
        anonymized = _make_anonymized(blocks={})
        scoring_result = _make_scoring_result(
            strengths=[Strength(code="HAS_EXP", message="Includes experience section")]
        )
        prompt = build_roast_prompt(anonymized=anonymized, scoring_result=scoring_result)
        assert "Includes experience section" in prompt

    def test_word_count_in_prompt(self):
        anonymized = _make_anonymized(blocks={}, metrics={"word_count": 312})
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "312" in prompt

    def test_prompt_describes_the_required_task(self):
        # Output *shape* (verdict/roast/fixes/highlights/quality_flags) is
        # enforced by Gemini's response_schema now, not by text labels in
        # the prompt (see workers/llm/pipeline/client.py) -- this just
        # checks the prompt still asks for the right content.
        anonymized = _make_anonymized(blocks={})
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "roast" in prompt.lower()
        assert "verdict" in prompt.lower()
        assert "HIGHLIGHTS" in prompt

    def test_prompt_asks_for_the_substance_score_and_its_rubric(self):
        # substance_score is the number the user actually sees, and the
        # rubric is the only thing calibrating it -- if the prompt stops
        # carrying either, scoring silently reverts to vibes.
        anonymized = _make_anonymized(blocks={})
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "substance_score" in prompt
        assert "substance_reasoning" in prompt
        for band in ("90-100", "70-89", "50-69", "0-49"):
            assert band in prompt

    def test_prompt_warns_against_scoring_on_polish_alone(self):
        # The eval's key finding: the model over-rewards the presence of
        # digits and formatting polish over evidence of real work.
        anonymized = _make_anonymized(blocks={})
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        # Normalized: the template hard-wraps, so these sentences span lines.
        flat = " ".join(prompt.split())
        assert "Judge the WORK, not the writing polish" in flat
        assert "Do not reward the mere presence of digits" in flat

    def test_prompt_says_quality_flags_do_not_affect_the_score(self):
        # Flags are explanatory only now. If the prompt lets the model
        # believe they're penalties, it double-counts them against
        # substance_score.
        anonymized = _make_anonymized(blocks={})
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "do NOT affect the score" in prompt

    def test_prompt_contains_quality_flag_instructions(self):
        anonymized = _make_anonymized(blocks={})
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        for code in (
            "GENERIC_BULLETS",
            "NO_QUANTIFIED_IMPACT",
            "BUZZWORD_FILLER",
            "WEAK_ACTION_LANGUAGE",
            "SHALLOW_CONTENT",
        ):
            assert code in prompt

    def test_prompt_contains_quantified_impact_grounding_line(self):
        anonymized = _make_anonymized(
            blocks={"experience": [{"text": "Cut latency by 40%\nManaged a team"}]}
        )
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "1 of 2 experience/project lines contain a number or percentage" in prompt

    def test_raises_on_missing_content(self):
        bad_anonymized = {"session_id": "x", "metrics": {}}
        with pytest.raises(ValueError, match="missing 'content'"):
            build_roast_prompt(
                anonymized=bad_anonymized,
                scoring_result=_make_scoring_result(),
            )

    def test_raises_on_bad_blocks_type(self):
        bad_anonymized = {"content": {"blocks": "not-a-dict"}, "metrics": {}}
        with pytest.raises(ValueError, match="not a dict"):
            build_roast_prompt(
                anonymized=bad_anonymized,
                scoring_result=_make_scoring_result(),
            )

    def test_empty_blocks_handled_gracefully(self):
        anonymized = _make_anonymized(blocks={})
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "no content extracted" in prompt

    def test_no_raw_pii_instruction_in_prompt(self):
        """Verify the prompt instructs the LLM not to reveal PII."""
        anonymized = _make_anonymized(blocks={})
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "PII" in prompt or "real name" in prompt

    def test_fixes_must_name_the_specific_offending_text(self):
        # A real user read the fix "Consolidate the duplicated sections and
        # standardize your layout" as "merge my Experience and Open Source
        # sections" -- which is not what it meant, and would have made their
        # resume worse. Fixes that only give a general directive leave the
        # reader guessing which part of their own document is wrong.
        #
        # Highlights have been grounded in verbatim resume text since they
        # were introduced; this asserts fixes carry the same requirement, so
        # the instruction cannot be quietly dropped back to "be actionable".
        anonymized = _make_anonymized(blocks={})
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "name the SPECIFIC thing" in prompt
        assert "without having to guess" in prompt
        # The banned-verb list is the operative half: these are exactly the
        # words that produced the ambiguous fix in the first place.
        for vague_verb in ("consolidate", "standardize", "improve", "optimize"):
            assert vague_verb in prompt


# ---------------------------------------------------------------------------
# _label_link_dumps
# ---------------------------------------------------------------------------

def _body_lines(n):
    """n distinct, ordinary content lines, to push a run out of the header zone."""
    return "\n".join(f"Built thing number {i} for the platform." for i in range(n))


class TestLinkDumpLabelling:
    """
    Tika appends a PDF's hyperlink TARGETS as plain text at the end of EACH
    PAGE. The candidate sees the word "GradeIT" on their page; we see a list of
    raw URLs they cannot find anywhere. The model then gave advice about text
    that is not on the resume.

    The first version only looked at the very end of the document, which
    covered every one-page PDF and missed every multi-page one. These pin both
    what must be labelled and -- more importantly -- what must NOT be, because
    the mid-document rule can now reach real content.

    The function never deletes: a wrong label costs a little roast coverage, a
    wrong deletion costs the candidate their content.
    """

    def test_trailing_link_dump_is_labelled(self):
        rendered = (
            "[WORK EXPERIENCE]\n" + _body_lines(10) + "\n"
            "[URL_1]\n[URL_2]\n[URL_3]\n[EMAIL_1]"
        )
        out = _label_link_dumps(rendered)
        assert out.count(_LINK_DUMP_NOTE) == 1
        assert out.index(_LINK_DUMP_NOTE) < out.index("[URL_1]")

    def test_mid_document_link_dump_is_labelled(self):
        # The two-page-PDF case: page 1's list sits before page 2's content.
        rendered = (
            "[WORK EXPERIENCE]\n" + _body_lines(12) + "\n"
            "[URL_1]\n[URL_2]\n[URL_3]\n[URL_4]\n\n"
            "[CERTIFICATIONS]\nAWS Solutions Architect"
        )
        out = _label_link_dumps(rendered)
        assert out.count(_LINK_DUMP_NOTE) == 1
        # sits before the run and NOT after it
        assert out.index(_LINK_DUMP_NOTE) < out.index("[URL_1]")
        # and the content that follows is untouched
        assert out.index("[URL_4]") < out.index("[CERTIFICATIONS]")

    def test_each_pages_link_list_is_labelled_once(self):
        rendered = (
            "[WORK EXPERIENCE]\n" + _body_lines(12) + "\n"
            "[URL_1]\n[URL_2]\n[URL_3]\n\n"
            "[PROJECTS]\n" + _body_lines(6) + "\n"
            "[URL_4]\n[URL_5]\n[URL_6]"
        )
        out = _label_link_dumps(rendered)
        assert out.count(_LINK_DUMP_NOTE) == 2

    def test_blank_lines_inside_a_run_do_not_split_it(self):
        rendered = (
            "[WORK EXPERIENCE]\n" + _body_lines(12) + "\n"
            "[URL_1]\n\n[URL_2]\n\n[URL_3]\n\n[CERTIFICATIONS]\nAWS SA"
        )
        assert _label_link_dumps(rendered).count(_LINK_DUMP_NOTE) == 1

    def test_nothing_is_deleted(self):
        rendered = (
            "[OTHER]\nJane Doe\n[WORK EXPERIENCE]\n" + _body_lines(12) + "\n"
            "[URL_1]\n[URL_2]\n[URL_3]\n[CERTIFICATIONS]\nAWS SA"
        )
        out = _label_link_dumps(rendered)
        for kept in ("Jane Doe", "[URL_1]", "[URL_2]", "[URL_3]", "AWS SA"):
            assert kept in out
        # every original line survives, in order; only notes were added
        assert [l for l in out.splitlines() if l != _LINK_DUMP_NOTE] == rendered.splitlines()

    def test_stacked_contact_header_at_the_top_is_left_alone(self):
        # The false positive a mid-document rule invites: a contact block
        # written one item per line looks exactly like a short link dump, and
        # telling the model the candidate's own email is invisible file
        # metadata would be wrong.
        rendered = (
            "[OTHER]\nJane Doe\n[EMAIL_1]\n[URL_1]\n[URL_2]\n\n"
            "[WORK EXPERIENCE]\n" + _body_lines(10)
        )
        assert _label_link_dumps(rendered) == rendered

    def test_a_run_containing_a_phone_number_is_never_a_dump(self):
        # The hidden list holds URLs and mailto: targets. A phone means this
        # is the candidate's visible contact block -- even at the very end.
        rendered = "[WORK EXPERIENCE]\n" + _body_lines(12) + "\n[EMAIL_1]\n[PHONE_1]\n[URL_1]"
        assert _label_link_dumps(rendered) == rendered

    def test_two_links_are_left_alone(self):
        rendered = "[WORK EXPERIENCE]\n" + _body_lines(12) + "\n[URL_1]\n[URL_2]"
        assert _label_link_dumps(rendered) == rendered

    def test_links_with_words_are_left_alone(self):
        # A real, human-written links section carries labels.
        rendered = (
            "[OTHER]\n" + _body_lines(12) + "\n"
            "Portfolio: [URL_1]\nGitHub: [URL_2]\nLinkedIn: [URL_3]"
        )
        assert _label_link_dumps(rendered) == rendered

    def test_resume_without_a_dump_is_untouched(self):
        rendered = "[SUMMARY / OBJECTIVE]\nBackend engineer.\n\n[EDUCATION]\nState University"
        assert _label_link_dumps(rendered) == rendered

    def test_empty_input(self):
        assert _label_link_dumps("") == ""

    def test_end_to_end_through_format_resume_sections(self):
        # The real shape: page 1's list is inside the last block of page 1,
        # and the next section starts page 2.
        blocks = {
            "other": [{"text": "Jane Doe\n{{EMAIL_1}} | {{PHONE_1}}",
                       "source_span": {"start": 0, "end": 40}}],
            "experience": [{"text": "Experience\n" + _body_lines(12),
                            "source_span": {"start": 100, "end": 900},
                            "heading": "Experience"}],
            "projects": [{"text": "Projects\nBuilt a thing.\n{{URL_1}}\n{{URL_2}}\n{{URL_3}}\n{{URL_4}}",
                          "source_span": {"start": 1000, "end": 1200},
                          "heading": "Projects"}],
            "certifications": [{"text": "Certifications\nAWS SA",
                                "source_span": {"start": 1300, "end": 1400},
                                "heading": "Certifications"}],
        }
        out = _format_resume_sections(blocks)
        assert out.count(_LINK_DUMP_NOTE) == 1
        assert out.index(_LINK_DUMP_NOTE) < out.index("[URL_1]")
        assert out.index("[URL_4]") < out.index("[CERTIFICATIONS]")


# ---------------------------------------------------------------------------
# _strip_own_heading / heading shown once
# ---------------------------------------------------------------------------

class TestHeadingShownOnce:
    """
    The segmenter keeps a section's heading as the first line of its block, and
    the prompt prints its own [SECTION] label above every block, so the model
    saw "Summary" twice and sometimes told the candidate to delete the
    "redundant" one (roughly 1 roast in 6).
    """

    def test_heading_is_not_repeated_under_its_label(self):
        blocks = {"summary": [{"text": "Summary\nBackend engineer.",
                               "source_span": {"start": 0, "end": 30},
                               "heading": "Summary"}]}
        out = _format_resume_sections(blocks)
        assert out == "[SUMMARY / OBJECTIVE]\nBackend engineer."

    def test_only_the_heading_line_is_removed(self):
        blocks = {"experience": [{"text": "Experience\nBuilt A.\nBuilt B.\nBuilt C.",
                                  "source_span": {"start": 0, "end": 60},
                                  "heading": "Experience"}]}
        out = _format_resume_sections(blocks)
        for kept in ("Built A.", "Built B.", "Built C."):
            assert kept in out
        assert "Experience\n" not in out

    def test_qualified_heading_is_removed_too(self):
        blocks = {"summary": [{"text": "Professional Summary\nBackend engineer.",
                               "source_span": {"start": 0, "end": 40},
                               "heading": "Professional Summary"}]}
        assert "Professional Summary" not in _format_resume_sections(blocks)

    def test_block_without_the_field_is_left_exactly_as_it_was(self):
        # Artifacts written before the field existed. Old behaviour, unchanged.
        blocks = {"summary": [{"text": "Summary\nBackend engineer.",
                               "source_span": {"start": 0, "end": 30}}]}
        assert _format_resume_sections(blocks) == "[SUMMARY / OBJECTIVE]\nSummary\nBackend engineer."

    def test_a_heading_that_is_not_the_first_line_is_never_stripped(self):
        # The field is only trusted when it actually matches, so a mismatch
        # can never delete real content.
        blocks = {"summary": [{"text": "Something else\nBackend engineer.",
                               "source_span": {"start": 0, "end": 30},
                               "heading": "Summary"}]}
        assert "Something else" in _format_resume_sections(blocks)

    def test_a_section_that_is_only_a_heading_still_shows_as_present(self):
        # An empty "Projects" section is information: keep the label.
        blocks = {"projects": [{"text": "Projects",
                                "source_span": {"start": 0, "end": 8},
                                "heading": "Projects"}]}
        assert "[PROJECTS]" in _format_resume_sections(blocks)

    def test_first_line_match_ignores_surrounding_whitespace(self):
        assert _strip_own_heading({"heading": "Summary"}, "Summary  \nBody") == "Body"

    def test_non_string_heading_is_ignored(self):
        assert _strip_own_heading({"heading": 7}, "Summary\nBody") == "Summary\nBody"


# ---------------------------------------------------------------------------
# Segment -> render: nothing but headings may ever disappear
# ---------------------------------------------------------------------------

class TestNoContentLostBetweenSegmenterAndPrompt:
    """
    The heading de-duplication deletes a line from the prompt, so the property
    that matters is: after segmenting and rendering, EVERY line of the original
    that is not purely a heading is still there. An earlier draft failed this on
    "Summary: Backend engineer, five years." -- the line starts with a heading
    word but carries content, and it was deleted along with the heading.
    """

    DOCS = {
        "plain": "Jane Doe\n\nSummary\nBackend engineer.\n\nExperience\nBuilt X in 2022.\n\nEducation\nState U\n",
        "inline summary": "Jane Doe\n\nSummary: Backend engineer, five years.\nBuilt payment APIs.\n\nEducation\nState U\n",
        "inline experience": "Jane Doe\n\nExperience: Acme Corp, Engineer, 2021 - present\nBuilt X.\n\nEducation\nState U\n",
        "qualified": "Jane Doe\n\nProfessional Summary\nBackend engineer.\n\nProfessional Experience\nAcme, 2021 - now\nBuilt X.\n",
        "colon heading": "Jane Doe\n\nProfessional Summary:\nBackend engineer.\n\nSkills:\nPython, Go\n",
        "heading-only section": "Jane Doe\nBackend engineer with five years of experience.\n\nProjects\n\nEducation\nState University, B.Sc., 2021\n",
        "indented headings": "Jane Doe\n\n\tSummary\nBackend engineer.\n\n\tEducation\nState U\n",
        "sentence that looks like a heading": "Jane Doe\n\nSummary\nBackend engineer.\nProfessional experience in Python and Go\n\nEducation\nState U\n",
    }

    @staticmethod
    def _is_pure_heading(line):
        from workers.normalization.pipeline.segmenter import SECTION_PATTERNS
        s = line.strip().rstrip(":").strip()
        return bool(s) and len(s) <= 50 and any(p.match(s) for p in SECTION_PATTERNS.values()) \
            and ":" not in line.strip()[:-1]

    def test_every_non_heading_line_survives(self):
        from workers.normalization.pipeline.segmenter import segment_text
        for name, raw in self.DOCS.items():
            rendered = _format_resume_sections(segment_text(raw))
            for line in raw.splitlines():
                if not line.strip() or self._is_pure_heading(line):
                    continue
                assert line.strip() in rendered, (
                    f"[{name}] lost a content line: {line.strip()!r}\n--- rendered ---\n{rendered}")

    def test_legitimate_duplicate_headings_are_still_removed(self):
        from workers.normalization.pipeline.segmenter import segment_text
        rendered = _format_resume_sections(segment_text(self.DOCS["plain"]))
        assert "Summary\n" not in rendered
        assert "Education\n" not in rendered
        assert "[SUMMARY / OBJECTIVE]" in rendered
