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
- composite_score/stamp are computed from scored.json's issues merged with
  roast.json's LLM-issued quality_issues (merge_quality_into_summary) --
  content-quality problems (generic bullets, no quantified impact, etc.)
  the rule engine structurally can't detect, so a resume with clean
  sections but hollow content no longer scores as if it had none.
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


_VALID_SEVERITIES = ("critical", "high", "medium", "low")


def merge_quality_into_summary(
    summary: Dict[str, Any], quality_issues: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Fold roast.json's LLM-issued quality_issues into a copy of scored.json's
    summary counts -- same shape in, same shape out, so compute_score and
    compute_stamp don't need to know two different issue sources exist.

    Quality issues never carry "critical" severity (see workers/llm/schemas
    .py's QUALITY_SEVERITY -- the LLM only ever assesses high/medium/low
    content-quality codes), but this reads whatever severity string shows
    up rather than assuming, so it stays correct if that ever changes.

    Checks against _VALID_SEVERITIES rather than "is this key already in
    the summary dict" -- scored.json's summary always has all 5 keys in
    practice (ScoreSummary requires them), but the merge shouldn't silently
    drop a real severity just because a caller's dict happened not to
    pre-populate that key at zero.
    """
    merged = dict(summary)
    for issue in quality_issues:
        severity = issue.get("severity")
        if severity not in _VALID_SEVERITIES:
            continue
        key = f"{severity}_issues"
        merged[key] = merged.get(key, 0) + 1
        merged["total_issues"] = merged.get("total_issues", 0) + 1
    return merged


def compute_score(summary: Dict[str, Any]) -> int:
    """
    Deterministic 0-100 composite score from a summary's issue counts
    (scored.json's own counts, or merge_quality_into_summary's merged
    result -- this function doesn't care which).

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
    summary = merge_quality_into_summary(scored["summary"], roast.get("quality_issues", []))

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
