"""
workers/scoring/schemas.py

Contract layer for the scoring worker.
Defines queue message, internal result, and final artifact schemas.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import List, Dict, Any
from enum import Enum


# ------------------------------------------------------------
# Version
# ------------------------------------------------------------

SCORING_VERSION = "1.0"


# ------------------------------------------------------------
# Enums
# ------------------------------------------------------------

class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ------------------------------------------------------------
# Queue Message
# ------------------------------------------------------------

class ScoringJobMessage(BaseModel):
    version: str = Field(..., example="1.0")
    job_type: str = Field(..., example="Scoring")

    session_id: UUID
    anonymized_blob_path: str

    attempt: int = 1
    created_at: datetime


# ------------------------------------------------------------
# Issue + Strength
# ------------------------------------------------------------

class Issue(BaseModel):
    code: str
    message: str
    severity: Severity


class Strength(BaseModel):
    code: str
    message: str


# ------------------------------------------------------------
# Summary
# ------------------------------------------------------------

class ScoreSummary(BaseModel):
    total_issues: int
    critical_issues: int
    high_issues: int
    medium_issues: int
    low_issues: int
    total_strengths: int


# ------------------------------------------------------------
# Internal Scoring Result (scorer.py → assembler.py)
# ------------------------------------------------------------

class ScoringResult(BaseModel):
    issues: List[Issue]
    strengths: List[Strength]


# ------------------------------------------------------------
# Final Artifact (scored.json)
# ------------------------------------------------------------

class ScoredOutput(BaseModel):
    session_id: str
    scoring_version: str = SCORING_VERSION

    summary: ScoreSummary

    issues: List[Issue]
    strengths: List[Strength]

    signals: Dict[str, Any]
    metrics: Dict[str, Any]

    timestamps: Dict[str, str]