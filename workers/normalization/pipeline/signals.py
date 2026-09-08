"""
Signals computation for normalization pipeline.

Responsibilities:
- Compute boolean / categorical resume signals
- No scoring, no numeric metrics
- No text mutation or redaction
- Deterministic and explainable

Signals feed:
- Rule engine
- Scoring
- LLM prompts (later)
"""

import re
from typing import Dict, Any


# ============================================================
# Regex patterns
# ============================================================

YEAR_REGEX = re.compile(r"(19|20)\d{2}")
FIRST_PERSON_REGEX = re.compile(r"\b(i|me|my|mine)\b", re.I)


# ============================================================
# Public API
# ============================================================

def compute_signals(
    *,
    blocks: Dict[str, list],
    entities: Dict[str, list],
    raw_text: str,
) -> Dict[str, bool]:
    """
    Compute deterministic resume signals:
    - Section presence
    - Contact info
    - Links
    - Dates in experience
    - Basic first-person usage

    A previous "Tier 2" here ran spaCy (context-aware first person, passive
    voice, action verbs) behind a `use_advanced_nlp` flag that defaulted to
    False and was never turned on in production -- the model
    (en_core_web_sm) was never even bundled into any worker image, so
    Tier 2 always silently degraded to its dummy fallback. Removed rather
    than wired up: PASSIVE_VOICE/NO_ACTION_VERBS as rule-engine checks are
    now superseded by the LLM's WEAK_ACTION_LANGUAGE quality flag (see
    workers/llm/schemas.py), which judges the same thing with actual
    language understanding instead of a fixed 21-verb list + a raw
    auxpass-dependency count -- no reason to run both.
    """

    signals: Dict[str, bool] = {}

    # ---- Section presence ----
    signals["has_summary"] = bool(blocks.get("summary"))
    signals["has_experience"] = bool(blocks.get("experience"))
    signals["has_projects"] = bool(blocks.get("projects"))
    signals["has_skills"] = bool(blocks.get("skills"))
    signals["has_education"] = bool(blocks.get("education"))
    signals["has_certifications"] = bool(blocks.get("certifications"))

    # ---- Contact info ----
    signals["has_email"] = bool(entities.get("emails"))
    signals["has_phone"] = bool(entities.get("phones"))
    signals["has_contact_info"] = (
        signals["has_email"] or signals["has_phone"]
    )

    # ---- Links ----
    urls = entities.get("urls", [])
    signals["has_links"] = bool(urls)

    # Professional links (LinkedIn / GitHub / Portfolio)
    signals["has_professional_links"] = any(
        any(domain in url.get("value", "").lower()
            for domain in ("linkedin.com", "github.com", "portfolio"))
        for url in urls
    )

    # ---- Dates in experience ----
    has_dates = False
    for block in blocks.get("experience", []):
        if YEAR_REGEX.search(block.get("text", "")):
            has_dates = True
            break
    signals["has_dates_in_experience"] = has_dates

    # ---- Basic first-person usage ----
    basic_fp_count = len(FIRST_PERSON_REGEX.findall(raw_text))
    signals["uses_first_person_basic"] = basic_fp_count >= 2

    return signals
