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


def compute_score(summary: Dict[str, Any]) -> int:
    """
    Deterministic 0-100 composite score from scored.json's summary counts.

    100 - 20*critical - 10*high - 5*medium - 2*low, clamped to [0, 100].
    """
    score = (
        100
        - 20 * summary.get("critical_issues", 0)
        - 10 * summary.get("high_issues", 0)
        - 5 * summary.get("medium_issues", 0)
        - 2 * summary.get("low_issues", 0)
    )
    return max(0, min(100, score))


def compute_stamp(summary: Dict[str, Any]) -> str:
    """Dynamic stamp badge tier, replacing the reference's hardcoded "ROASTED"."""
    critical = summary.get("critical_issues", 0)
    high = summary.get("high_issues", 0)
    total_issues = summary.get("total_issues", 0)
    total_strengths = summary.get("total_strengths", 0)

    if critical > 0 or high >= 2:
        return "ROASTED"
    if total_issues == 0 and total_strengths >= 3:
        return "SOLID"
    return "MID"


def build_card_context(
    *,
    scored: Dict[str, Any],
    roast: Dict[str, Any],
    display_name: str,
) -> Dict[str, Any]:
    """Assembles the full Jinja2 template context for roast_card.html."""
    summary = scored["summary"]

    return {
        "candidate_name": display_name,
        "punchline": roast["verdict"],
        "stamp": compute_stamp(summary),
        "score": compute_score(summary),
        "stat2_label": "Issues Found",
        "stat2_value": str(summary.get("total_issues", 0)),
        "resume_lines": RESUME_SNIPPET_LINES,
        "cta_text": CTA_TEXT,
    }
