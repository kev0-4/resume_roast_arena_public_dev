from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class InterviewStartResponse(BaseModel):
    """
    Everything the browser needs to run the interview itself.

    `token` is a single-use ephemeral Gemini credential, NOT our API key.
    It cannot be re-minted for the same interview, which is why a refresh
    of the live page can never resume a session.

    `tools` is passed through to the browser's own connect config so both
    sides declare the same thing. The authoritative copy is the one pinned
    into the token itself.

    `resume_text` backs the in-room reference pane -- the same anonymized
    resume the interviewer is reading, never the roast (which would hand
    the candidate the list of weak spots they're about to be asked about).
    """
    interview_id: str
    token: str
    model: str
    system_instruction: str
    tools: list[dict]
    resume_text: str
    # The round agenda, shown to the candidate before they join so the
    # interview's shape is never a surprise mid-session.
    agenda: list[dict] = Field(default_factory=list)
    expires_at: datetime


class InterviewRoundResponse(BaseModel):
    """One exercise round's question, stripped of anything that would give
    the answer away. See catalogue.public_question."""
    index: int
    minutes: int
    question: dict


class InterviewDryRunResult(BaseModel):
    """
    A read of the code for languages we cannot execute in the browser.

    Not a test result, and the UI must not present it as one -- nothing was
    run. It exists so a Java or C++ candidate gets some feedback rather
    than nothing at all.
    """
    looks_correct: bool
    summary: str
    problems: list[str]


class InterviewRoundResult(BaseModel):
    """
    What the candidate is told after submitting.

    Deliberately excludes the review's `interviewer_notes` -- that is
    ammunition for the debrief, and showing it would let them prepare for
    the exact question coming next.
    """
    index: int
    score: int
    strengths: list[str]
    problems: list[str]
    mcq_detail: Optional[list[dict]] = None
    next_round_kind: Optional[str] = None
    next_round_index: Optional[int] = None


class InterviewTranscriptAck(BaseModel):
    accepted: int
    total_chunks: int


class InterviewEndedEarly(BaseModel):
    """Reported by the browser when the interviewer called end_interview."""
    reason: str = Field(default="", max_length=500)
    category: str = Field(default="COMPLETE", max_length=40)


class InterviewCompleteRequest(BaseModel):
    # Both come from the interviewer's own tool calls during the session.
    # Client-reported, like the transcript itself -- same trust boundary,
    # documented on the transcript route.
    skipped_questions: int = Field(default=0, ge=0, le=100)
    ended_early: Optional[InterviewEndedEarly] = None


class InterviewScoreResult(BaseModel):
    interview_id: str
    status: str
    score: int
    strengths: list[str]
    weaknesses: list[str]
    next_steps: list[str]


class TranscriptEntry(BaseModel):
    """One merged speaker turn, not a raw streamed fragment."""
    seq: int
    speaker: str
    text: str
    at: Optional[str] = None


class InterviewDetailResponse(BaseModel):
    interview_id: str
    status: str
    resume_session_id: str
    roast_slug: Optional[str] = None
    job_description: str
    transcript: list[TranscriptEntry]
    score: Optional[int] = None
    strengths: Optional[list[str]] = None
    weaknesses: Optional[list[str]] = None
    next_steps: Optional[list[str]] = None
    started_at: datetime
    completed_at: Optional[datetime] = None


class InterviewLeaderboardEntry(BaseModel):
    rank: int
    display_name: str
    score: int
    completed_at: datetime


class InterviewLeaderboardResponse(BaseModel):
    total: int
    limit: int
    offset: int
    entries: list[InterviewLeaderboardEntry]


class MyInterviewLeaderboardPosition(BaseModel):
    rank: int
    total: int
    score: int
    completed_at: datetime


class MyInterviewEntry(BaseModel):
    """
    One row of a candidate's own interview history -- every status, not
    just COMPLETED. Unlike the leaderboard (which only ever shows a
    scored, eligible interview), this is the candidate's own record of
    what they actually did, including a run that never finished.
    """
    id: str
    status: str
    score: Optional[int] = None
    vertical: Optional[str] = None
    job_description: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class MyInterviewsResponse(BaseModel):
    total: int
    limit: int
    offset: int
    interviews: list[MyInterviewEntry]


class InterviewEligibilityResponse(BaseModel):
    eligible: bool
    resume_session_id: Optional[str] = None
