"""
Tests for backend/src/interview/validator.py -- pure functions, no I/O,
no real Gemini calls (those are for manual/throwaway verification, not
the checked-in suite).

Only scoring is validated here now. The per-turn validators are gone with
the turn-based interview: the conversation happens over the Live API, in
the browser, and never produces a structured turn response to validate.
"""

from .schemas import InterviewScoreResponse
from .validator import validate_score_response


def _score_response(**overrides) -> InterviewScoreResponse:
    defaults = dict(
        score=7,
        strengths=["Specific about the caching layer's design."],
        weaknesses=["Couldn't quantify the impact."],
        next_steps=["Practice giving numbers."],
    )
    defaults.update(overrides)
    return InterviewScoreResponse(**defaults)


class TestValidateScoreResponse:
    def test_in_range_score_passes_through(self):
        assert validate_score_response(_score_response(score=7)).score == 7

    def test_boundaries_pass_through(self):
        assert validate_score_response(_score_response(score=1)).score == 1
        assert validate_score_response(_score_response(score=10)).score == 10

    def test_above_range_is_clamped_not_rejected(self):
        assert validate_score_response(_score_response(score=15)).score == 10

    def test_below_range_is_clamped_not_rejected(self):
        assert validate_score_response(_score_response(score=-3)).score == 1

    def test_empty_strengths_gets_fallback_not_empty_list(self):
        result = validate_score_response(_score_response(strengths=[]))
        assert len(result.strengths) >= 1
        assert result.strengths[0].strip() != ""

    def test_all_blank_weaknesses_gets_fallback(self):
        result = validate_score_response(_score_response(weaknesses=["  ", ""]))
        assert len(result.weaknesses) >= 1
        assert result.weaknesses[0].strip() != ""

    def test_mix_of_real_and_blank_keeps_only_real(self):
        result = validate_score_response(
            _score_response(next_steps=["Real step.", "  ", "Another real one."])
        )
        assert result.next_steps == ["Real step.", "Another real one."]
