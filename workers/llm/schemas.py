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
    Content-quality checks the rule engine structurally can't make -- these
    require actually judging whether the writing is good, not just whether
    a section exists. Deliberately a small fixed enum, same spirit as
    workers/scoring/pipeline/rules.py's issue codes: the LLM only ever
    decides yes/no per code (see QUALITY_SEVERITY below for why it never
    assigns its own severity), so scores stay comparable and auditable
    across resumes instead of the model inventing arbitrary categories or
    weights each time.
    """
    GENERIC_BULLETS = "GENERIC_BULLETS"
    NO_QUANTIFIED_IMPACT = "NO_QUANTIFIED_IMPACT"
    BUZZWORD_FILLER = "BUZZWORD_FILLER"
    WEAK_ACTION_LANGUAGE = "WEAK_ACTION_LANGUAGE"
    SHALLOW_CONTENT = "SHALLOW_CONTENT"


# Severity is owned here, not by the model -- the LLM only ever returns
# *which* codes apply (see LLMStructuredResponse.quality_flags), never a
# severity for them. Same point values as workers/scoring/pipeline/rules.py
# uses for its HIGH/MEDIUM/LOW issues, so a quality flag costs exactly as
# much as an equivalent-severity structural one once merged into one score.
QUALITY_SEVERITY: Dict[QualityIssueCode, str] = {
    QualityIssueCode.GENERIC_BULLETS: "high",
    QualityIssueCode.NO_QUANTIFIED_IMPACT: "high",
    QualityIssueCode.BUZZWORD_FILLER: "medium",
    QualityIssueCode.WEAK_ACTION_LANGUAGE: "medium",
    QualityIssueCode.SHALLOW_CONTENT: "low",
}


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


class QualityIssue(BaseModel):
    """
    One quality flag the LLM raised, with severity attached by us (see
    QUALITY_SEVERITY) -- never by the model itself. Same shape as
    workers/scoring/pipeline/schemas.py's Issue on purpose: both get
    merged into one set of severity counts downstream (renderer's
    compute_score, backend's radar-chart subscores), so keeping the shape
    identical means that merge is just "concatenate two lists," not a
    field-mapping exercise.
    """
    code: QualityIssueCode
    severity: str


class LLMStructuredResponse(BaseModel):
    """
    The exact shape asked of Gemini via response_schema (JSON mode) --
    passed directly as GenerateContentConfig.response_schema, so this
    class *is* the API contract with the model, not just an internal
    convenience type. quality_flags carries codes only, never severity;
    the caller (processor.py) attaches severity via QUALITY_SEVERITY
    before this becomes a QualityIssue.
    """
    verdict: str
    roast: str
    fixes: List[str]
    highlights: List[Highlight] = []
    quality_flags: List[QualityIssueCode] = []


class RoastResult(BaseModel):
    """Parsed output from the LLM, after grounding + severity attachment."""
    verdict: str
    roast: str
    fixes: List[str]
    highlights: List[Highlight] = []
    quality_issues: List[QualityIssue] = []


class RoastOutput(BaseModel):
    """Final artifact saved as roast.json."""
    session_id: str
    roast_version: str = ROAST_VERSION

    verdict: str
    roast: str
    fixes: List[str]
    highlights: List[Highlight] = []
    quality_issues: List[QualityIssue] = []

    model: str
    usage: Dict[str, int]

    timestamps: Dict[str, str]
