"""
workers/renderer/pipeline/card_data.py

Pure functions turning scored.json + roast.json + a display name into the
template context for the roast card.

Design decisions (see MIGRATION DOCS/Resume_Roast_Arena_Project_Documentation.md
section 29):
- composite_score is a lightweight 0-100 score derived from scored.json's
  issue/strength counts -- NOT the original MVP's unimplemented
  Clarity/Credibility/Signal-to-Noise composite scoring. It's stored on
  Sessions.composite_score (queryable, for a future leaderboard), not just
  rendered as pixels.
- stamp is computed the same way, replacing the reference component's
  hardcoded "ROASTED".
- v1 ships with hardcoded resume-snippet lines (matching the reference
  component's defaultResumeLines) -- a real-anonymized-snippet mode is a
  deferred future toggle, not built here.
- composite_score = roast.json's substance_score (the LLM's holistic 0-100
  content judgment) minus the rule engine's structural deductions, and the
  stamp is derived from that score rather than from issue counts. Replaced
  a design that deducted fixed points per binary quality flag, which a real
  eval showed compressed everything into a 32-point band and couldn't tell
  mediocre from bad -- see quality-scoring-eval/REPORT.md.
"""

from typing import Dict, Any, List


# ---------------------------------------------------------------------------
# v1 hardcoded resume snippet (ported from the reference component)
# ---------------------------------------------------------------------------

RESUME_SNIPPET_LINES: List[str] = [
    "SUMMARY",
    "Results-driven synergy enthusiast",
    "",
    "EXPERIENCE",
    "Senior Manager of Being Busy",
    "Assistant to the Regional Buzzwords",
    'Led cross-functional "initiatives"',
    "",
    "SKILLS",
    "Microsoft Word (Advanced)",
    "Team Player, Self Starter, Ninja",
]

CTA_TEXT = "resumeroastarena.com"  # placeholder -- no real domain yet


def structural_deduction(summary: Dict[str, Any]) -> int:
    """
    Points the rule engine's structural issues cost (missing sections, bad
    length, no contact info, etc.) -- 20/critical, 10/high, 5/medium,
    2/low, the same weights this file has always used.
    """
    return (
        20 * summary.get("critical_issues", 0)
        + 10 * summary.get("high_issues", 0)
        + 5 * summary.get("medium_issues", 0)
        + 2 * summary.get("low_issues", 0)
    )


def compute_score(summary: Dict[str, Any], substance_score: int | None = None) -> int:
    """
    0-100 composite score: the LLM's holistic substance judgment
    (roast.json's substance_score) as the baseline, minus what the rule
    engine's structural issues cost. Clamped to [0, 100].

    Reads as "your content is worth 75, and you lose 10 more for having no
    projects section" -- content quality dominates, structure adjusts.

    `substance_score=None` falls back to a flat 100 baseline, i.e. pure
    structural scoring. That's the pre-substance-score behaviour, kept for
    sessions whose roast.json predates the field (nothing migrates old
    artifacts) rather than scoring them as if their content were worthless.

    Why substance is a baseline rather than a set of point deductions: the
    previous design deducted fixed points per binary quality flag, which a
    real 25-resume eval showed compressed every result into a 32-point band
    (a deliberately content-free resume floored at 68/100) and could not
    separate mediocre from bad, because the flags are correlated symptoms
    that fire together. One holistic judgment measured a 90-point spread on
    the same set and tracked human tier labels better. See
    quality-scoring-eval/REPORT.md.
    """
    baseline = 100 if substance_score is None else substance_score
    return max(0, min(100, baseline - structural_deduction(summary)))


SOLID_MIN_SCORE = 85
MID_MIN_SCORE = 60


def compute_stamp(score: int) -> str:
    """
    Stamp badge tier, derived from the final composite score.

    Was derived from structural issue counts alone ("critical > 0 or
    high >= 2 -> ROASTED; no issues and 3+ strengths -> SOLID"). That
    breaks under substance scoring: a resume with every section present
    but content-free writing has zero structural issues and would have
    been stamped SOLID while scoring in the single digits. Deriving the
    tier from the score it's displayed next to keeps the two from ever
    contradicting each other.

    Thresholds calibrated against the eval set (quality-scoring-eval/):
    metric-rich and strong technical resumes land 85-95 (SOLID), real but
    under-sold resumes 65-80 (MID), duty-description and buzzword resumes
    5-45 (ROASTED).
    """
    if score >= SOLID_MIN_SCORE:
        return "SOLID"
    if score >= MID_MIN_SCORE:
        return "MID"
    return "ROASTED"


def build_card_context(
    *,
    scored: Dict[str, Any],
    roast: Dict[str, Any],
    display_name: str,
) -> Dict[str, Any]:
    """Assembles the full Jinja2 template context for roast_card.html."""
    summary = scored["summary"]
    score = compute_score(summary, roast.get("substance_score"))

    return {
        "candidate_name": display_name,
        "punchline": roast["verdict"],
        "stamp": compute_stamp(score),
        "score": score,
        "stat2_label": "Issues Found",
        # Structural issues plus the named quality flags -- the flags no
        # longer cost points (substance_score does the scoring now) but
        # they're still real, user-visible things to fix, so the card's
        # count shouldn't pretend they don't exist.
        "stat2_value": str(summary.get("total_issues", 0) + len(roast.get("quality_flags", []))),
        "resume_lines": RESUME_SNIPPET_LINES,
        "cta_text": CTA_TEXT,
    }
