"""
workers/llm/schemas.py

Contract layer for the LLM roast worker.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import List, Dict
from enum import Enum


ROAST_VERSION = "1.0"


class QualityIssueCode(str, Enum):
    """
    Named content-quality problems the LLM can point at. These are
    EXPLANATORY ONLY -- they tell the user what to fix, and they do not
    affect the score at all (substance_score does that, see below).

    They used to be the scoring mechanism: each flag carried a fixed
    severity and deducted points. A real eval against 25 synthetic resumes
    plus 3 real ones killed that design -- 5 binary flags with fixed point
    values compressed everything into a 32-point band (a deliberately
    content-free resume floored at 68/100) and couldn't separate mediocre
    from bad at all, because the flags are correlated symptoms of one root
    problem and fire as a bundle. See quality-scoring-eval/REPORT.md.
    """
    GENERIC_BULLETS = "GENERIC_BULLETS"
    NO_QUANTIFIED_IMPACT = "NO_QUANTIFIED_IMPACT"
    BUZZWORD_FILLER = "BUZZWORD_FILLER"
    WEAK_ACTION_LANGUAGE = "WEAK_ACTION_LANGUAGE"
    SHALLOW_CONTENT = "SHALLOW_CONTENT"


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


SUBSTANCE_SCORE_MIN = 0
SUBSTANCE_SCORE_MAX = 100


class LLMStructuredResponse(BaseModel):
    """
    The exact shape asked of Gemini via response_schema (JSON mode) --
    passed directly as GenerateContentConfig.response_schema, so this
    class *is* the API contract with the model, not just an internal
    convenience type.

    substance_score is the scoring signal: one holistic 0-100 judgment of
    how much real evidence of meaningful work the resume actually gives,
    against the rubric in workers/scoring/pipeline/prompt_builder.py.
    quality_flags are explanatory only -- they name what to fix and never
    touch the number (see QualityIssueCode's docstring for why the old
    flag-deduction scoring was replaced).
    """
    verdict: str
    roast: str
    fixes: List[str]
    highlights: List[Highlight] = []
    substance_score: int
    substance_reasoning: str
    quality_flags: List[QualityIssueCode] = []


class RoastResult(BaseModel):
    """Parsed output from the LLM, after grounding + range validation."""
    verdict: str
    roast: str
    fixes: List[str]
    highlights: List[Highlight] = []
    substance_score: int
    substance_reasoning: str
    quality_flags: List[QualityIssueCode] = []


class RoastOutput(BaseModel):
    """Final artifact saved as roast.json."""
    session_id: str
    roast_version: str = ROAST_VERSION

    verdict: str
    roast: str
    fixes: List[str]
    highlights: List[Highlight] = []
    substance_score: int
    substance_reasoning: str
    quality_flags: List[QualityIssueCode] = []

    model: str
    usage: Dict[str, int]

    timestamps: Dict[str, str]
