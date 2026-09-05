"""
Unit tests for workers/llm/pipeline/validator.py

Run with:  python -m pytest workers/llm/pipeline/test_validator.py -v
"""

import pytest
from .validator import parse_roast_output, _split_sections, _parse_fixes
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
