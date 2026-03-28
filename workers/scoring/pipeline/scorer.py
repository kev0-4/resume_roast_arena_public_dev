"""
workers/scoring/pipeline/scorer.py
Scorer for scoring pipeline.

Responsibilities:
- Call rule engine
- Normalize outputs
- Return ScoringResult
"""

from typing import Dict, Any, List

from ..schemas import ScoringResult, Issue, Strength
from .rules import evaluate_rules


# ------------------------------------------------------------
# MAIN ENTRYPOINT
# ------------------------------------------------------------
def score_resume(
    *,
    signals: Dict[str, Any],
    metrics: Dict[str, Any],
    blocks: Dict[str, list],
) -> ScoringResult:
    """
    Compute scoring result from signals + metrics.
    """

    # ------------------------------------------------------------
    # 1. Apply rules
    # ------------------------------------------------------------
    issues, strengths = evaluate_rules(
        signals=signals,
        metrics=metrics,
        blocks=blocks,
    )

    # ------------------------------------------------------------
    # 2. Normalize outputs
    # ------------------------------------------------------------
    issues = _dedupe_issues(issues)
    strengths = _dedupe_strengths(strengths)

    # ------------------------------------------------------------
    # 3. Return structured result
    # ------------------------------------------------------------
    return ScoringResult(
        issues=issues,
        strengths=strengths,
    )


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------
def _dedupe_issues(issues: List[Issue]) -> List[Issue]:
    """
    Remove duplicate issues based on (code, severity).
    """
    seen = set()
    unique: List[Issue] = []

    for issue in issues:
        key = (issue.code, issue.severity)

        if key not in seen:
            seen.add(key)
            unique.append(issue)

    return unique


def _dedupe_strengths(strengths: List[Strength]) -> List[Strength]:
    """
    Remove duplicate strengths based on code.
    """
    seen = set()
    unique: List[Strength] = []

    for strength in strengths:
        if strength.code not in seen:
            seen.add(strength.code)
            unique.append(strength)

    return unique