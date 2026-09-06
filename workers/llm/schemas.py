"""
workers/llm/schemas.py

Contract layer for the LLM roast worker.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import List, Dict


ROAST_VERSION = "1.0"


class LLMJobMessage(BaseModel):
    version: str = Field(..., json_schema_extra={"example": "1.0"})
    job_type: str = Field(..., json_schema_extra={"example": "LLMRoast"})

    session_id: UUID
    prompt_blob_path: str

    attempt: int = 1
    created_at: datetime


class Highlight(BaseModel):
    """
    One quoted excerpt from the resume + a roast comment on it.

    `quote` must be a verbatim substring of the anonymized resume text the
    LLM was shown (enforced by validator.py's grounding check, not by this
    schema) -- the whole point is that these are real words from the
    resume, not the LLM's paraphrase or invention.
    """
    quote: str
    comment: str


class RoastResult(BaseModel):
    """Parsed output from the LLM."""
    verdict: str
    roast: str
    fixes: List[str]
    highlights: List[Highlight] = []


class RoastOutput(BaseModel):
    """Final artifact saved as roast.json."""
    session_id: str
    roast_version: str = ROAST_VERSION

    verdict: str
    roast: str
    fixes: List[str]
    highlights: List[Highlight] = []

    model: str
    usage: Dict[str, int]

    timestamps: Dict[str, str]
