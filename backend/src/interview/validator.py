"""
backend/src/interview/validator.py

Turns raw Gemini responses into safe-to-use values -- mirrors
workers/llm/pipeline/validator.py's clamp/ground philosophy: response_schema
guarantees *shape*, not that a field is meaningful or in range.

Deliberately lenient rather than raising on empty/malformed feedback
fields (unlike parse_roast_output's "fixes has no actionable items"
ValueError): an interview's final scoring call failing would strand the
session at turn_count == max_turns with no way to submit another turn and
no score (the "stuck IN_PROGRESS" failure mode the implementation plan
flags explicitly) -- a fallback string is a much better outcome for a
user who just spent several minutes on a live interview than an error
page. Falls back to a generic string per empty list, not silently empty
content and not a hard failure.
"""

from typing import List

from .schemas import InterviewTurnResponse, InterviewScoreResponse, SCORE_MIN, SCORE_MAX

_FALLBACK_REACTION = "Noted."
_FALLBACK_NEXT_QUESTION = "Let's move on -- walk me through another part of your resume."
_FALLBACK_CLOSING = "That's a wrap. Let's see how you did."


def validate_turn_response(
    response: InterviewTurnResponse, *, turn_count: int, max_turns: int
) -> InterviewTurnResponse:
    """
    turn_count is the interview's turn_count BEFORE this turn is recorded
    (i.e. the turn currently being answered) -- is_final_turn is
    force-set True once answering this turn would bring turn_count to
    max_turns, regardless of what the model itself returned. This is the
    actual hard-cap enforcement point: the model's own is_final_turn is
    only ever allowed to end an interview EARLY, never to extend it past
    the cap.
    """
    is_final = response.is_final_turn or (turn_count + 1 >= max_turns)

    reaction_text = response.reaction_text.strip() or _FALLBACK_REACTION
    next_question = response.next_question.strip()
    if not next_question:
        next_question = _FALLBACK_CLOSING if is_final else _FALLBACK_NEXT_QUESTION

    return InterviewTurnResponse(
        answer_transcript=response.answer_transcript.strip(),
        reaction_text=reaction_text,
        next_question=next_question,
        is_final_turn=is_final,
    )


_FALLBACK_OPENING_QUESTION = "Walk me through the most recent thing on your resume -- what did you actually do?"


def validate_opening_question(response: InterviewTurnResponse) -> str:
    """
    The opening call has no prior answer to react to or transcribe, so
    only next_question is meaningful here -- returns the validated
    question text alone rather than a full InterviewTurnResponse.
    """
    return response.next_question.strip() or _FALLBACK_OPENING_QUESTION


def _non_empty_or_fallback(items: List[str], fallback: str) -> List[str]:
    cleaned = [i.strip() for i in items if i.strip()]
    return cleaned or [fallback]


def validate_score_response(response: InterviewScoreResponse) -> InterviewScoreResponse:
    # Clamped, not rejected -- same reasoning as substance_score's clamp:
    # a fumbled out-of-range number is the model missing a number, not a
    # reason to fail a score the user is waiting on.
    score = max(SCORE_MIN, min(SCORE_MAX, response.score))

    return InterviewScoreResponse(
        score=score,
        strengths=_non_empty_or_fallback(response.strengths, "Showed up and answered every question."),
        weaknesses=_non_empty_or_fallback(response.weaknesses, "Answers could have been more specific."),
        next_steps=_non_empty_or_fallback(response.next_steps, "Practice giving concrete, quantified examples."),
    )
