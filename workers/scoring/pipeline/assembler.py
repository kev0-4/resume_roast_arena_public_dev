"""
workers/scoring/pipeline/assembler.py
Assembler for scoring pipeline.

Responsibilities:
- Build scored.json artifact
- Compute summary
- Preserve upstream data
"""

from typing import Dict, Any, List
from datetime import datetime
from uuid import UUID

from ..schemas import (
    ScoringResult,
    ScoredOutput,
    ScoreSummary,
    Issue,
    Severity,
)
from ..errors import PermanentScoringError

SCORING_VERSION = "1.0"


# ------------------------------------------------------------
# MAIN ASSEMBLER
# ------------------------------------------------------------
def assemble_scored(
    *,
    session_id: str | UUID,
    anonymized: Dict[str, Any],
    scoring_result: ScoringResult,
    scored_at: datetime,
) -> Dict[str, Any]:
    """
    Assemble final scored.json artifact.
    """

    # ------------------------------------------------------------
    # 1. Minimal validation
    # ------------------------------------------------------------
    if not isinstance(anonymized, dict):
        raise PermanentScoringError("anonymized payload must be a dict")

    if "signals" not in anonymized or "metrics" not in anonymized:
        raise PermanentScoringError("missing signals or metrics in anonymized payload")

    timestamps = anonymized.get("timestamps")
    if not isinstance(timestamps, dict):
        raise PermanentScoringError("missing timestamps in anonymized payload")

    # ------------------------------------------------------------
    # 2. Compute summary
    # ------------------------------------------------------------
    summary = _build_summary(scoring_result.issues, scoring_result.strengths)

    # ------------------------------------------------------------
    # 3. Build final artifact
    # ------------------------------------------------------------
    scored: Dict[str, Any] = {
        "session_id": str(session_id),
        "scoring_version": SCORING_VERSION,

        "summary": summary,

        "issues": [issue.model_dump() for issue in scoring_result.issues],
        "strengths": [s.model_dump() for s in scoring_result.strengths],

        "signals": anonymized["signals"],
        "metrics": anonymized["metrics"],

        "timestamps": {
            "anonymized_at": timestamps.get("anonymized_at"),
            "scored_at": scored_at.isoformat(),
        },
    }

    return scored


# ------------------------------------------------------------
# SUMMARY BUILDER
# ------------------------------------------------------------
def _build_summary(
    issues: List[Issue],
    strengths: List[Any],
) -> Dict[str, int]:
    """
    Compute severity breakdown and totals.
    """

    summary = {
        "total_issues": len(issues),
        "critical_issues": 0,
        "high_issues": 0,
        "medium_issues": 0,
        "low_issues": 0,
        "total_strengths": len(strengths),
    }

    for issue in issues:
        if issue.severity == Severity.CRITICAL:
            summary["critical_issues"] += 1
        elif issue.severity == Severity.HIGH:
            summary["high_issues"] += 1
        elif issue.severity == Severity.MEDIUM:
            summary["medium_issues"] += 1
        elif issue.severity == Severity.LOW:
            summary["low_issues"] += 1

    return summary