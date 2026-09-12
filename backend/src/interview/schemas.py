"""
backend/src/interview/schemas.py

Contract layer for the mock-interview feature's one remaining Gemini
text call -- same philosophy as workers/llm/schemas.py's
LLMStructuredResponse: this class *is* the response_schema passed directly
to GenerateContentConfig, not just an internal convenience type.

The conversation itself no longer goes through a structured-output call at
all. It happens over the Live API, in the browser, as audio -- so there is
no per-turn schema any more, only scoring.
"""

from typing import List
from pydantic import BaseModel


SCORE_MIN = 1
SCORE_MAX = 10


class InterviewScoreResponse(BaseModel):
    """
    Asked of Gemini once, after the live session ends, over the full
    speaker-tagged transcript the browser streamed up during the call.
    """
    score: int
    strengths: List[str]
    weaknesses: List[str]
    next_steps: List[str]
