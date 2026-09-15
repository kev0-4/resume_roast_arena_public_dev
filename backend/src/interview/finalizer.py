"""
backend/src/interview/finalizer.py

Ending an IN_PROGRESS interview, from nothing but what the server already
stored. Two callers, deliberately sharing one implementation:

  1. POST /interview/{id}/complete -- the browser reached the end (the end
     button, the timer, the interviewer's own end_interview tool).
  2. The cleanup worker's stale sweep -- the browser never reached the end
     at all, because the tab was closed. Nothing else ever transitioned
     those rows, so they sat IN_PROGRESS forever.

The rule is the same either way, which is the point of sharing it: a
transcript with real candidate speech gets scored, silence gets marked
ABANDONED. Closing the tab three minutes from the end should cost the
candidate the last three minutes, not the whole interview and not the one
interview a week they were allowed to start.

Raises rather than returning an HTTP shape, so the worker is not importing
FastAPI concepts to sweep a table -- the route maps ScoringUnavailable onto
its own 503.
"""

import logging
from typing import Any, Dict, Literal, Optional, Tuple

from google.genai import errors as genai_errors
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.interview_sessions import InterviewSessions
from . import artifacts
from . import llm_client as interview_llm
from . import prompt_builder as interview_prompts
from . import service as interview_service
from . import validator as interview_validator

logger = logging.getLogger(__name__)

Outcome = Literal["scored", "abandoned"]


class ScoringUnavailable(Exception):
    """
    Gemini could not be reached to grade this interview.

    Deliberately distinct from "this interview has nothing worth grading":
    the interview stays IN_PROGRESS so the next sweep retries it. A transient
    quota error must not be the thing that permanently abandons someone's
    interview.
    """


async def finalize_in_progress_interview(
    db: AsyncSession,
    interview: InterviewSessions,
    *,
    skipped_questions: int = 0,
    ended_early: Optional[Dict[str, Any]] = None,
) -> Tuple[Outcome, InterviewSessions]:
    """
    Scores an in-progress interview, or marks it abandoned if the candidate
    never actually said anything.

    The caller is responsible for checking status first -- this function
    assumes it has been handed a genuinely IN_PROGRESS row.

    skipped_questions/ended_early are the interviewer's own conduct report,
    which only exists when the browser made it to /complete. The sweep has
    no way to know them and passes the defaults: an interview finalized
    from a closed tab is graded on its transcript alone.
    """
    chunks = await artifacts.read_transcript(interview)
    utterances = interview_service.merge_into_utterances(chunks)

    # Nothing the candidate said means nothing to grade. Ending here avoids
    # spending a Gemini call on silence and keeps an empty session off the
    # leaderboard entirely.
    if not any(u["speaker"] == "candidate" for u in utterances):
        interview = await interview_service.mark_interview_abandoned(db, interview)
        return "abandoned", interview

    anonymized, roast = await artifacts.load_resume_context(interview.resume_session_id)
    system_context = interview_prompts.build_interview_system_context(
        anonymized, roast, interview.job_description
    )
    scoring_prompt = interview_prompts.build_scoring_prompt(
        system_context,
        utterances,
        skipped_questions=skipped_questions,
        ended_early=ended_early,
        # Server-side record of the graded exercises. Read from the row
        # rather than accepted from the client: these grades were decided
        # here, against answer keys and expected outputs that never left
        # this process.
        round_results=interview.round_results or [],
    )

    try:
        raw_score, _usage, _model = await interview_llm.generate_score(scoring_prompt)
    except genai_errors.APIError as e:
        raise ScoringUnavailable(str(e)) from e

    validated = interview_validator.validate_score_response(raw_score)
    interview = await interview_service.finalize_interview(db, interview, validated)
    return "scored", interview
