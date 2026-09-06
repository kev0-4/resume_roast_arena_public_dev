"""
Unit tests for workers/llm/pipeline/validator.py

Run with:  python -m pytest workers/llm/pipeline/test_validator.py -v
"""

import pytest
from .validator import parse_roast_output, _split_sections, _parse_fixes, _parse_highlights
from ..schemas import RoastResult


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

GOOD_OUTPUT = """\
VERDICT: This resume is a monument to vagueness — impressive only in its commitment to saying nothing.

ROAST:
The summary reads like a fortune cookie had a LinkedIn phase. Phrases like "results-driven" and "team player" appear with no evidence to back them up. The work experience section lists job titles and dates but omits any quantified impact — what did you ship? What changed because you were there? The skills section is a bingo card of buzzwords (Python, SQL, Agile, Leadership) with zero context for when or how they were applied.

The education section is fine — but that bar is low. Listing your GPA from four years ago when you have three years of experience suggests you haven't done anything in those three years you're more proud of.

FIXES:
- Replace every soft-skills cliché ("team player", "results-driven") with a concrete achievement and a number.
- Add 2–3 bullet points per role that answer: what did you build, what was the impact, and how did you measure it?
- Move the skills section below experience and trim it to the 5–8 skills most relevant to the roles you're targeting.
"""

MINIMAL_OUTPUT = """\
VERDICT: A resume that aspires to mediocrity and barely achieves it.

ROAST:
Not much to say — the content is thin.

FIXES:
- Add more content.
- Quantify everything.
- Proofread.
"""


# ---------------------------------------------------------------------------
# _split_sections
# ---------------------------------------------------------------------------

class TestSplitSections:
    def test_extracts_all_three_sections(self):
        sections = _split_sections(GOOD_OUTPUT)
        assert "VERDICT" in sections
        assert "ROAST" in sections
        assert "FIXES" in sections

    def test_verdict_is_single_line(self):
        sections = _split_sections(GOOD_OUTPUT)
        assert "\n" not in sections["VERDICT"]
        assert "monument to vagueness" in sections["VERDICT"]

    def test_roast_is_multiline(self):
        sections = _split_sections(GOOD_OUTPUT)
        assert "\n" in sections["ROAST"]

    def test_fixes_contains_bullet_lines(self):
        sections = _split_sections(GOOD_OUTPUT)
        assert "Replace every" in sections["FIXES"]

    def test_empty_string_returns_empty_dict(self):
        assert _split_sections("") == {}

    def test_missing_section_not_in_result(self):
        text = "VERDICT: Something.\n\nROAST:\nSome roast."
        sections = _split_sections(text)
        assert "VERDICT" in sections
        assert "ROAST" in sections
        assert "FIXES" not in sections

    def test_verdict_inline_content(self):
        text = "VERDICT: Inline verdict here.\nROAST:\nBody.\nFIXES:\n- Fix."
        sections = _split_sections(text)
        assert sections["VERDICT"] == "Inline verdict here."


# ---------------------------------------------------------------------------
# _parse_fixes
# ---------------------------------------------------------------------------

class TestParseFixes:
    def test_dash_bullets(self):
        fixes = _parse_fixes("- Fix one.\n- Fix two.\n- Fix three.")
        assert fixes == ["Fix one.", "Fix two.", "Fix three."]

    def test_bullet_character(self):
        fixes = _parse_fixes("• Fix A\n• Fix B")
        assert fixes == ["Fix A", "Fix B"]

    def test_numbered_list(self):
        fixes = _parse_fixes("1. Fix one\n2. Fix two")
        assert fixes == ["Fix one", "Fix two"]

    def test_blank_lines_skipped(self):
        fixes = _parse_fixes("- Fix A\n\n- Fix B")
        assert fixes == ["Fix A", "Fix B"]

    def test_empty_string_returns_empty(self):
        assert _parse_fixes("") == []

    def test_star_bullets(self):
        fixes = _parse_fixes("* Fix X\n* Fix Y")
        assert fixes == ["Fix X", "Fix Y"]


# ---------------------------------------------------------------------------
# parse_roast_output (integration)
# ---------------------------------------------------------------------------

class TestParseRoastOutput:
    def test_returns_roast_result(self):
        result = parse_roast_output(GOOD_OUTPUT)
        assert isinstance(result, RoastResult)

    def test_verdict_extracted(self):
        result = parse_roast_output(GOOD_OUTPUT)
        assert "monument to vagueness" in result.verdict

    def test_roast_extracted(self):
        result = parse_roast_output(GOOD_OUTPUT)
        assert "fortune cookie" in result.roast

    def test_fixes_list(self):
        result = parse_roast_output(GOOD_OUTPUT)
        assert isinstance(result.fixes, list)
        assert len(result.fixes) == 3

    def test_fixes_content(self):
        result = parse_roast_output(GOOD_OUTPUT)
        assert any("cliché" in f or "soft" in f.lower() or "Replace" in f for f in result.fixes)

    def test_minimal_output(self):
        result = parse_roast_output(MINIMAL_OUTPUT)
        assert result.verdict
        assert result.roast
        assert len(result.fixes) == 3

    def test_raises_on_missing_verdict(self):
        text = "ROAST:\nSome roast.\nFIXES:\n- Fix."
        with pytest.raises(ValueError, match="missing required section"):
            parse_roast_output(text)

    def test_raises_on_missing_roast(self):
        text = "VERDICT: Something.\nFIXES:\n- Fix."
        with pytest.raises(ValueError, match="missing required section"):
            parse_roast_output(text)

    def test_raises_on_missing_fixes(self):
        text = "VERDICT: Something.\nROAST:\nSome roast."
        with pytest.raises(ValueError, match="missing required section"):
            parse_roast_output(text)

    def test_raises_on_empty_fixes(self):
        # An empty FIXES section (parsed as "") is falsy, so it's caught
        # by the "missing required section" guard before reaching the
        # "no actionable items" check — both are ValueError.
        text = "VERDICT: Something.\nROAST:\nBody.\nFIXES:\n"
        with pytest.raises(ValueError):
            parse_roast_output(text)

    def test_raises_on_blank_fixes_content(self):
        # FIXES section has content but all items are empty after stripping bullets.
        # "- " (dash then space, no text) → cleaned to "" → filtered out → no items.
        text = "VERDICT: Something.\nROAST:\nBody.\nFIXES:\n- \n- \n"
        with pytest.raises(ValueError, match="no actionable items"):
            parse_roast_output(text)

    def test_raises_on_empty_string(self):
        with pytest.raises(ValueError):
            parse_roast_output("")

    def test_whitespace_only_input(self):
        with pytest.raises(ValueError):
            parse_roast_output("   \n\n   ")

    def test_verdict_is_string(self):
        result = parse_roast_output(MINIMAL_OUTPUT)
        assert isinstance(result.verdict, str)
        assert len(result.verdict) > 0

    def test_roast_is_string(self):
        result = parse_roast_output(MINIMAL_OUTPUT)
        assert isinstance(result.roast, str)
        assert len(result.roast) > 0

    def test_extra_whitespace_handled(self):
        text = (
            "VERDICT:  Verdict with extra spaces.  \n\n"
            "ROAST:\n  Roast with indentation.\n\n"
            "FIXES:\n  - Fix A\n  - Fix B\n"
        )
        result = parse_roast_output(text)
        assert result.verdict == "Verdict with extra spaces."
        assert "Roast with indentation." in result.roast
        assert "Fix A" in result.fixes
        assert "Fix B" in result.fixes


# ---------------------------------------------------------------------------
# _parse_highlights (grounding check)
# ---------------------------------------------------------------------------

SOURCE_TEXT = """\
[SUMMARY]
Results-driven synergy enthusiast with a passion for leveraging cross-functional paradigms.

[EXPERIENCE]
Led cross-functional initiatives to drive stakeholder alignment.
Managed a team of 3 engineers on the checkout redesign project.
"""


class TestParseHighlights:
    def test_grounded_quote_is_kept(self):
        text = '"Results-driven synergy enthusiast" :: A thesaurus had a seizure here.'
        highlights = _parse_highlights(text, SOURCE_TEXT)
        assert len(highlights) == 1
        assert highlights[0].quote == "Results-driven synergy enthusiast"
        assert "thesaurus" in highlights[0].comment

    def test_hallucinated_quote_is_dropped(self):
        text = '"Invented Cold Fusion in my garage" :: Bold claim, zero evidence.'
        highlights = _parse_highlights(text, SOURCE_TEXT)
        assert highlights == []

    def test_mix_of_grounded_and_hallucinated(self):
        text = (
            '"Results-driven synergy enthusiast" :: Real, and rough.\n'
            '"Invented Cold Fusion" :: Not real -- should be dropped.\n'
            '"Managed a team of 3 engineers" :: At least this one is concrete.'
        )
        highlights = _parse_highlights(text, SOURCE_TEXT)
        quotes = [h.quote for h in highlights]
        assert "Results-driven synergy enthusiast" in quotes
        assert "Managed a team of 3 engineers" in quotes
        assert "Invented Cold Fusion" not in quotes
        assert len(highlights) == 2

    def test_grounding_skipped_when_no_source_text(self):
        text = '"Anything at all" :: no source to check against.'
        highlights = _parse_highlights(text, "")
        assert len(highlights) == 1
        assert highlights[0].quote == "Anything at all"

    def test_whitespace_differences_still_match(self):
        # Quote spans what was two lines in the source, collapsed to one
        # line in the LLM's output -- still a real substring once
        # whitespace is normalized on both sides.
        text = '"Led cross-functional initiatives to drive stakeholder alignment" :: Buzzword soup.'
        highlights = _parse_highlights(text, SOURCE_TEXT)
        assert len(highlights) == 1

    def test_malformed_line_skipped_not_raised(self):
        text = "This line has no quote marks or :: delimiter at all."
        highlights = _parse_highlights(text, SOURCE_TEXT)
        assert highlights == []

    def test_empty_highlights_text_returns_empty_list(self):
        assert _parse_highlights("", SOURCE_TEXT) == []

    def test_blank_quote_or_comment_skipped(self):
        text = '"" :: empty quote should be skipped\n"Results-driven synergy enthusiast" :: '
        highlights = _parse_highlights(text, SOURCE_TEXT)
        assert highlights == []


class TestParseRoastOutputWithHighlights:
    def test_highlights_included_when_grounded(self):
        text = (
            "VERDICT: Fine.\nROAST:\nBody.\nFIXES:\n- Fix.\n"
            'HIGHLIGHTS:\n"Results-driven synergy enthusiast" :: Buzzword soup.\n'
        )
        result = parse_roast_output(text, source_text=SOURCE_TEXT)
        assert len(result.highlights) == 1
        assert result.highlights[0].quote == "Results-driven synergy enthusiast"

    def test_hallucinated_highlight_dropped_but_roast_still_parses(self):
        text = (
            "VERDICT: Fine.\nROAST:\nBody.\nFIXES:\n- Fix.\n"
            'HIGHLIGHTS:\n"Made up quote that is not in the resume" :: fabricated.\n'
        )
        result = parse_roast_output(text, source_text=SOURCE_TEXT)
        assert result.highlights == []
        assert result.verdict == "Fine."

    def test_missing_highlights_section_does_not_raise(self):
        result = parse_roast_output(MINIMAL_OUTPUT, source_text=SOURCE_TEXT)
        assert result.highlights == []

    def test_default_source_text_keeps_backward_compatible_signature(self):
        # Every pre-existing call site (and every other test in this file)
        # calls parse_roast_output(text) with one argument -- confirms
        # that still works exactly as before.
        result = parse_roast_output(GOOD_OUTPUT)
        assert isinstance(result, RoastResult)
        assert result.highlights == []
