from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class InterviewStartResponse(BaseModel):
    interview_id: str
    status: str
    turn_number: int
    max_turns: int
    question_text: str
    question_audio_url: str


class InterviewTurnApiResponse(BaseModel):
    """
    response_audio_url is ONE combined clip -- the reaction to the answer
    just given, spoken together with the next question (or, on the final
    turn, just the closing reaction alone) -- matching the one-TTS-call-
    per-turn design. Not two separate audio files.
    """
    interview_id: str
    turn_number: int
    reaction_text: str
    next_question: str
    response_audio_url: str
    is_final: bool
    status: str
    score: Optional[int] = None
    strengths: Optional[list[str]] = None
    weaknesses: Optional[list[str]] = None
    next_steps: Optional[list[str]] = None


class TranscriptTurnEntry(BaseModel):
    turn: int
    question_text: str
    question_audio_url: str
    answer_transcript: Optional[str] = None
    answer_audio_url: Optional[str] = None
    reaction_text: Optional[str] = None


class InterviewDetailResponse(BaseModel):
    interview_id: str
    status: str
    resume_session_id: str
    roast_slug: Optional[str] = None
    job_description: str
    turn_count: int
    max_turns: int
    transcript: list[TranscriptTurnEntry]
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
