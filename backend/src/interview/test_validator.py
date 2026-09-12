"""
Tests for backend/src/interview/validator.py -- pure functions, no I/O,
no real Gemini calls (those are for manual/throwaway verification, not
the checked-in suite).
"""

from .schemas import InterviewTurnResponse, InterviewScoreResponse
from .validator import (
    validate_turn_response,
    validate_opening_question,
    validate_score_response,
)


def _turn_response(**overrides) -> InterviewTurnResponse:
    defaults = dict(
        answer_transcript="I built a caching layer.",
        reaction_text="Vague. What kind of cache?",
        next_question="What eviction policy did you use?",
        is_final_turn=False,
    )
    defaults.update(overrides)
    return InterviewTurnResponse(**defaults)


class TestValidateTurnResponse:
    def test_passes_through_when_not_at_cap(self):
        result = validate_turn_response(_turn_response(), turn_count=1, max_turns=7)
        assert result.is_final_turn is False
        assert result.next_question == "What eviction policy did you use?"

    def test_respects_model_signaled_early_final(self):
        result = validate_turn_response(_turn_response(is_final_turn=True), turn_count=1, max_turns=7)
        assert result.is_final_turn is True

    def test_force_finalizes_at_the_cap_regardless_of_model(self):
        # turn_count=6, max_turns=7 -> answering this turn brings turn_count
        # to 7 == max_turns, so it must be forced final even though the
        # model said otherwise. This is the actual hard-cap enforcement.
        result = validate_turn_response(_turn_response(is_final_turn=False), turn_count=6, max_turns=7)
        assert result.is_final_turn is True

    def test_does_not_force_final_before_the_cap(self):
        result = validate_turn_response(_turn_response(is_final_turn=False), turn_count=5, max_turns=7)
        assert result.is_final_turn is False

    def test_empty_reaction_gets_fallback(self):
        result = validate_turn_response(_turn_response(reaction_text="   "), turn_count=0, max_turns=7)
        assert result.reaction_text.strip() != ""

    def test_empty_next_question_gets_fallback_when_not_final(self):
        result = validate_turn_response(_turn_response(next_question=""), turn_count=0, max_turns=7)
        assert result.next_question.strip() != ""

    def test_empty_next_question_gets_closing_fallback_when_final(self):
        result = validate_turn_response(
            _turn_response(next_question="", is_final_turn=True), turn_count=0, max_turns=7
        )
        assert result.next_question.strip() != ""

    def test_strips_whitespace(self):
        result = validate_turn_response(
            _turn_response(answer_transcript="  padded  ", reaction_text="  also padded  "),
            turn_count=0,
            max_turns=7,
        )
        assert result.answer_transcript == "padded"
        assert result.reaction_text == "also padded"


class TestValidateOpeningQuestion:
    def test_returns_question_text(self):
        response = _turn_response(next_question="Tell me about your last role.")
        assert validate_opening_question(response) == "Tell me about your last role."

    def test_empty_gets_fallback(self):
        response = _turn_response(next_question="   ")
        assert validate_opening_question(response).strip() != ""


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
