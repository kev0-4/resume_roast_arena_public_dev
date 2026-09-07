"""
Tests for workers/llm/pipeline/validator.py.

response_schema (JSON mode) now guarantees shape -- these tests cover what
it *can't* guarantee: non-empty content, HIGHLIGHTS grounding against the
real resume text, and severity attachment for quality_flags.
"""

import pytest

from .validator import parse_roast_output
from ..schemas import LLMStructuredResponse, Highlight, QualityIssueCode


def _response(**overrides) -> LLMStructuredResponse:
    defaults = dict(
        verdict="A verdict.",
        roast="A roast body.",
        fixes=["Fix one.", "Fix two."],
        highlights=[],
        quality_flags=[],
    )
    defaults.update(overrides)
    return LLMStructuredResponse(**defaults)


class TestBasicFields:
    def test_returns_roast_result(self):
        result = parse_roast_output(_response())
        assert result.verdict == "A verdict."
        assert result.roast == "A roast body."
        assert result.fixes == ["Fix one.", "Fix two."]

    def test_strips_whitespace(self):
        result = parse_roast_output(_response(verdict="  padded  ", roast="  also padded  "))
        assert result.verdict == "padded"
        assert result.roast == "also padded"

    def test_strips_and_drops_blank_fixes(self):
        result = parse_roast_output(_response(fixes=["  real fix  ", "   ", ""]))
        assert result.fixes == ["real fix"]


class TestRequiredFieldValidation:
    def test_raises_on_empty_verdict(self):
        with pytest.raises(ValueError, match="verdict"):
            parse_roast_output(_response(verdict=""))

    def test_raises_on_whitespace_only_verdict(self):
        with pytest.raises(ValueError, match="verdict"):
            parse_roast_output(_response(verdict="   "))

    def test_raises_on_empty_roast(self):
        with pytest.raises(ValueError, match="roast"):
            parse_roast_output(_response(roast=""))

    def test_raises_on_empty_fixes_list(self):
        with pytest.raises(ValueError, match="fixes"):
            parse_roast_output(_response(fixes=[]))

    def test_raises_on_all_blank_fixes(self):
        with pytest.raises(ValueError, match="fixes"):
            parse_roast_output(_response(fixes=["  ", ""]))


class TestHighlightGrounding:
    SOURCE = "Built a real-time data pipeline processing 2M events/day using Kafka and Python."

    def test_grounded_quote_is_kept(self):
        highlights = [Highlight(quote="Built a real-time data pipeline", comment="ok")]
        result = parse_roast_output(_response(highlights=highlights), source_text=self.SOURCE)
        assert len(result.highlights) == 1
        assert result.highlights[0].quote == "Built a real-time data pipeline"

    def test_hallucinated_quote_is_dropped(self):
        highlights = [Highlight(quote="Something never actually said", comment="ok")]
        result = parse_roast_output(_response(highlights=highlights), source_text=self.SOURCE)
        assert result.highlights == []

    def test_mix_of_grounded_and_hallucinated(self):
        highlights = [
            Highlight(quote="Built a real-time data pipeline", comment="real"),
            Highlight(quote="Invented nonsense quote", comment="fake"),
        ]
        result = parse_roast_output(_response(highlights=highlights), source_text=self.SOURCE)
        assert len(result.highlights) == 1
        assert result.highlights[0].comment == "real"

    def test_grounding_skipped_when_no_source_text(self):
        highlights = [Highlight(quote="anything at all", comment="ok")]
        result = parse_roast_output(_response(highlights=highlights), source_text="")
        assert len(result.highlights) == 1

    def test_whitespace_differences_still_match(self):
        highlights = [Highlight(quote="Built  a real-time\ndata pipeline", comment="ok")]
        result = parse_roast_output(_response(highlights=highlights), source_text=self.SOURCE)
        assert len(result.highlights) == 1

    def test_blank_quote_or_comment_dropped(self):
        highlights = [
            Highlight(quote="", comment="ok"),
            Highlight(quote="Built a real-time data pipeline", comment=""),
        ]
        result = parse_roast_output(_response(highlights=highlights), source_text=self.SOURCE)
        assert result.highlights == []

    def test_hallucinated_highlight_does_not_fail_the_whole_parse(self):
        highlights = [Highlight(quote="made up", comment="fake")]
        result = parse_roast_output(_response(highlights=highlights), source_text=self.SOURCE)
        assert result.verdict == "A verdict."
        assert result.highlights == []


class TestQualityIssueSeverityAttachment:
    def test_flags_get_correct_severity(self):
        result = parse_roast_output(
            _response(quality_flags=[QualityIssueCode.GENERIC_BULLETS, QualityIssueCode.SHALLOW_CONTENT])
        )
        by_code = {qi.code: qi.severity for qi in result.quality_issues}
        assert by_code[QualityIssueCode.GENERIC_BULLETS] == "high"
        assert by_code[QualityIssueCode.SHALLOW_CONTENT] == "low"

    def test_no_flags_means_no_quality_issues(self):
        result = parse_roast_output(_response(quality_flags=[]))
        assert result.quality_issues == []

    def test_duplicate_flags_are_deduped(self):
        result = parse_roast_output(
            _response(quality_flags=[QualityIssueCode.BUZZWORD_FILLER, QualityIssueCode.BUZZWORD_FILLER])
        )
        assert len(result.quality_issues) == 1

    def test_all_five_codes_map_to_a_severity(self):
        result = parse_roast_output(_response(quality_flags=list(QualityIssueCode)))
        assert len(result.quality_issues) == 5
        assert all(qi.severity in ("high", "medium", "low") for qi in result.quality_issues)
