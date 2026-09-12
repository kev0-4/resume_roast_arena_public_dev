from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class InterviewStartResponse(BaseModel):
    """
    Everything the browser needs to run the interview itself.

    `token` is a single-use ephemeral Gemini credential, NOT our API key.
    It cannot be re-minted for the same interview, which is why a refresh
    of the live page can never resume a session.
    """
    interview_id: str
    token: str
    model: str
    system_instruction: str
    expires_at: datetime


class InterviewTranscriptAck(BaseModel):
    accepted: int
    total_chunks: int


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


class InterviewEligibilityResponse(BaseModel):
    eligible: bool
    resume_session_id: Optional[str] = None
