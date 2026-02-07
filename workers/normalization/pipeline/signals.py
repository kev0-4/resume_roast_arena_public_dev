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
# Regex patterns (Tier 1 – always on)
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
    use_advanced_nlp: bool = False,  # IMPORTANT: OFF by default
) -> Dict[str, bool]:
    """
    Compute deterministic resume signals.

    Tier 1 (always):
    - Section presence
    - Contact info
    - Links
    - Dates in experience
    - Basic first-person usage

    Tier 2 (optional):
    - Context-aware first person
    - Passive voice
    - Action verbs
    """

    signals: Dict[str, bool] = {}

    # ============================================================
    # TIER 1: BASIC / REGEX SIGNALS
    # ============================================================

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

    # ============================================================
    # TIER 2: ADVANCED NLP SIGNALS (OPTIONAL)
    # ============================================================

    if use_advanced_nlp:
        nlp = _get_nlp()
        if nlp is not None:
            try:
                advanced = _compute_spacy_signals(
                    raw_text=raw_text,
                    experience_blocks=blocks.get("experience", []),
                    nlp=nlp,
                )
                signals.update(advanced)
                signals["nlp_analysis_successful"] = True
            except Exception:
                signals.update(_dummy_advanced_signals())
                signals["nlp_analysis_successful"] = False
        else:
            signals.update(_dummy_advanced_signals())
            signals["nlp_analysis_successful"] = False
    else:
        signals.update(_dummy_advanced_signals())
        signals["nlp_analysis_successful"] = False

    return signals


# ============================================================
# Tier 2 – spaCy-based signals (boolean only)
# ============================================================

def _compute_spacy_signals(
    *,
    raw_text: str,
    experience_blocks: list,
    nlp,
) -> Dict[str, bool]:
    """
    Compute context-aware linguistic signals using spaCy.
    Boolean outputs ONLY.
    """

    signals: Dict[str, bool] = {}

    doc = nlp(raw_text)

    # ---- Context-aware first person (global) ----
    fp_subjects = 0
    for token in doc:
        if (
            token.pos_ == "PRON"
            and token.text.lower() in {"i", "me", "my", "mine"}
            and token.dep_ in {"nsubj", "nsubjpass"}
        ):
            fp_subjects += 1

    signals["uses_first_person_contextual"] = fp_subjects >= 2

    # ---- First person specifically in experience ----
    exp_text = "\n".join(b.get("text", "") for b in experience_blocks)
    if exp_text:
        exp_doc = nlp(exp_text)
        exp_fp = sum(
            1 for t in exp_doc
            if (
                t.pos_ == "PRON"
                and t.text.lower() in {"i", "me", "my", "mine"}
                and t.dep_ in {"nsubj", "nsubjpass"}
            )
        )
        signals["uses_first_person_in_experience"] = exp_fp >= 2
    else:
        signals["uses_first_person_in_experience"] = False

    # ---- Passive voice ----
    passive_count = sum(1 for t in doc if t.dep_ == "auxpass")
    signals["uses_passive_voice"] = passive_count >= 3

    # ---- Action verbs ----
    ACTION_VERBS = {
        "lead", "manage", "build", "develop", "create", "design",
        "implement", "launch", "deliver", "improve", "optimize",
        "establish", "coordinate", "spearhead", "achieve", "drive",
        "execute", "enhance", "streamline", "architect", "pioneer",
    }

    action_hits = 0
    for token in doc:
        if token.pos_ == "VERB" and token.lemma_.lower() in ACTION_VERBS:
            # bonus if sentence-initial / bullet-start
            if token.i == 0 or doc[token.i - 1].is_punct:
                action_hits += 1

    signals["has_action_verbs"] = action_hits >= 3

    return signals


# ============================================================
# Fallback when NLP unavailable
# ============================================================

def _dummy_advanced_signals() -> Dict[str, bool]:
    """
    Returned when spaCy is unavailable or disabled.
    Represents 'unknown', not False judgment.
    """
    return {
        "uses_first_person_contextual": False,
        "uses_first_person_in_experience": False,
        "uses_passive_voice": False,
        "has_action_verbs": False,
    }


# ============================================================
# spaCy lazy loader
# ============================================================

_nlp_model = None


def _get_nlp():
    """
    Lazy-load spaCy model.
    Gracefully degrades if spaCy is unavailable.
    """
    global _nlp_model

    if _nlp_model is None:
        try:
            import spacy
            _nlp_model = spacy.load("en_core_web_sm")
        except Exception:
            _nlp_model = False

    return _nlp_model if _nlp_model is not False else None
