"""
backend/src/interview/validator.py

Turns raw Gemini responses into safe-to-use values -- mirrors
workers/llm/pipeline/validator.py's clamp/ground philosophy: response_schema
guarantees *shape*, not that a field is meaningful or in range.

Deliberately lenient rather than raising on empty/malformed feedback
fields (unlike parse_roast_output's "fixes has no actionable items"
ValueError): the scoring call happens after the candidate has already
spent real minutes talking, and there is nothing left to retry by then --
a fallback string is a far better outcome for them than an error page.
Falls back to a generic string per empty list, not silently empty content
and not a hard failure.
"""

from typing import List

from .schemas import InterviewScoreResponse, SCORE_MIN, SCORE_MAX


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
