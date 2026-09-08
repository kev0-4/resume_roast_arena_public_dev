"""
Tests for workers/llm/pipeline/validator.py.

response_schema (JSON mode) now guarantees shape -- these tests cover what
it *can't* guarantee: non-empty content, HIGHLIGHTS grounding against the
real resume text, and substance_score being in range.
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
        substance_score=70,
        substance_reasoning="Real work, under-sold.",
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


class TestSubstanceScore:
    def test_in_range_score_passes_through(self):
        assert parse_roast_output(_response(substance_score=73)).substance_score == 73

    def test_boundaries_pass_through(self):
        assert parse_roast_output(_response(substance_score=0)).substance_score == 0
        assert parse_roast_output(_response(substance_score=100)).substance_score == 100

    def test_above_range_is_clamped_not_rejected(self):
        # A fumbled number shouldn't fail a whole roast the user is
        # waiting on -- and an unclamped 150 would produce a nonsense
        # composite score downstream.
        assert parse_roast_output(_response(substance_score=150)).substance_score == 100

    def test_below_range_is_clamped_not_rejected(self):
        assert parse_roast_output(_response(substance_score=-20)).substance_score == 0

    def test_reasoning_is_stripped(self):
        result = parse_roast_output(_response(substance_reasoning="  padded reason  "))
        assert result.substance_reasoning == "padded reason"


class TestQualityFlags:
    def test_flags_pass_through(self):
        result = parse_roast_output(
            _response(quality_flags=[QualityIssueCode.GENERIC_BULLETS, QualityIssueCode.SHALLOW_CONTENT])
        )
        assert result.quality_flags == [
            QualityIssueCode.GENERIC_BULLETS,
            QualityIssueCode.SHALLOW_CONTENT,
        ]

    def test_no_flags_means_empty_list(self):
        assert parse_roast_output(_response(quality_flags=[])).quality_flags == []

    def test_duplicate_flags_are_deduped_preserving_order(self):
        result = parse_roast_output(
            _response(
                quality_flags=[
                    QualityIssueCode.BUZZWORD_FILLER,
                    QualityIssueCode.GENERIC_BULLETS,
                    QualityIssueCode.BUZZWORD_FILLER,
                ]
            )
        )
        assert result.quality_flags == [
            QualityIssueCode.BUZZWORD_FILLER,
            QualityIssueCode.GENERIC_BULLETS,
        ]

    def test_all_five_codes_survive(self):
        result = parse_roast_output(_response(quality_flags=list(QualityIssueCode)))
        assert len(result.quality_flags) == 5

    def test_flags_do_not_affect_the_substance_score(self):
        # The point of the redesign: flags explain, they don't score.
        flagged = parse_roast_output(
            _response(substance_score=88, quality_flags=list(QualityIssueCode))
        )
        clean = parse_roast_output(_response(substance_score=88, quality_flags=[]))
        assert flagged.substance_score == clean.substance_score == 88
