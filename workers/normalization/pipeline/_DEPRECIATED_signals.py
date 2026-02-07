"""
Signals computation for normalization pipeline.

Responsibilities:
- Compute boolean / categorical resume signals
- No scoring, no judgment
- these signals feed scoring/rule/llm engine 
- input blocks(output of segmenter),entities(output of extractor), raw_text
- 2 Tier architecture (Tier 1 Regex based, tier 2 spacy based,llm fall back)
"""
'''
Flow -> Basic Regex always computed
if use_advanced_nlp = true,
 _compute_spacy_signals is invoked
 > checks first person texts, overall, in Experience
 > checks for passive voice
 > detects action verb (bonus if verb starts a sentence)
 > sentence quality 
 > vocabulry richness
 
'''

# TODO: _compute_metric_density and _check_bullet_consistency

import re
from typing import Dict, Any


YEAR_REGEX = re.compile(r"(19|20)\d{2}")
FIRST_PERSON_REGEX = re.compile(r"\b(i|me|my|mine)\b", re.I)
_ACTION_VERBS = {
    "lead", "manage", "build", "develop", "create", "design",
    "implement", "launch", "deliver", "improve", "optimize",
    "establish", "coordinate", "spearhead", "achieve", "drive",
    "execute", "enhance", "streamline", "architect", "pioneer"
}
_FIRST_PERSON_VERBS = {"i", "me", "my", "mine"}
_nlp_model = None


def compute_signals(
    *,
    blocks: Dict[str, list],
    entities: Dict[str, list],
    raw_text: str,
    use_advanced_nlp: bool = True,
) -> Dict[str, bool]:
    """
    Compute deterministic signals from normalized inputs.
    compute_signals()
├── Tier 1: Regex (always runs)
│   ├── Section presence ✅
│   ├── Contact info ✅
│   ├── Dates ✅
│   └── Basic first-person ✅
│
└── Tier 2: spaCy (optional, graceful fallback)
    ├── Context-aware first-person 🔄
    ├── Passive voice 🔄
    ├── Action verbs 🔄
    ├── Sentence quality 🔄
    └── Vocabulary metrics 🔄
    """

    signals: Dict[str, Any] = {}

    # ============================================================
    # TIER 1: REGEX-BASED SIGNALS (Always computed)
    # ============================================================

    # 1. Section presence
    signals["has_summary"] = bool(blocks.get("summary"))
    signals["has_experience"] = bool(blocks.get("experience"))
    signals["has_projects"] = bool(blocks.get("projects"))
    signals["has_skills"] = bool(blocks.get("skills"))
    signals["has_education"] = bool(blocks.get("education"))
    signals["has_certifications"] = bool(blocks.get("certifications"))

    # 2. Contact & links
    signals["has_email"] = bool(entities.get("emails"))
    signals["has_phone"] = bool(entities.get("phones"))
    signals["has_contact_info"] = signals["has_email"] or signals["has_phone"]

    urls = entities.get("urls", [])
    signals["has_links"] = bool(urls)

    # Professional links
    professional_link_count = 0
    for url_entity in urls:
        url = url_entity.get("value", "").lower()
        if any(domain in url for domain in ["linkedin.com", "github.com", "portfolio"]):
            professional_link_count += 1
    signals["has_professional_links"] = professional_link_count > 0

    # 3. Dates in experience
    experience_blocks = blocks.get("experience", [])
    date_count = 0
    for block in experience_blocks:
        matches = YEAR_REGEX.findall(block.get("text", ""))
        date_count += len(matches)

    signals["has_dates_in_experience"] = date_count > 0
    signals["experience_date_count"] = date_count

    # 4. Basic first-person detection (regex fallback)
    first_person_matches = FIRST_PERSON_REGEX.findall(raw_text)
    signals["first_person_count_basic"] = len(first_person_matches)
    signals["uses_first_person_basic"] = len(first_person_matches) >= 2

    # 5. Basic quality signals
    word_count = len(raw_text.split())
    signals["word_count"] = word_count
    signals["is_too_short"] = word_count < 100
    signals["is_too_long"] = word_count > 3000

    # ============================================================
    # TIER 2: SPACY-BASED SIGNALS (Context-aware)
    # ============================================================

    if use_advanced_nlp:
        nlp = _get_nlp()

        if nlp is not None:
            # spaCy available - compute advanced signals
            try:
                advanced_signals = _compute_spacy_signals(
                    raw_text, experience_blocks, nlp)
                signals.update(advanced_signals)
                signals["nlp_analysis_successful"] = True
            except Exception as e:
                print(f"[SIGNALS] spaCy analysis failed: {e}")
                # Fallback to dummy values
                signals.update(_get_dummy_advanced_signals())
                signals["nlp_analysis_successful"] = False
        else:
            # spaCy not available - use dummy values
            signals.update(_get_dummy_advanced_signals())
            signals["nlp_analysis_successful"] = False
    else:
        # Advanced NLP disabled by feature flag
        signals.update(_get_dummy_advanced_signals())
        signals["nlp_analysis_successful"] = False

    return signals
# ============================================================
# SPACY-BASED ANALYSIS (Tier 2)
# ============================================================


def _compute_spacy_signals(
    raw_text: str,
    experience_blocks: list,
    nlp
) -> Dict[str, Any]:
    """
    Compute advanced linguistic signals using spaCy.

    Args:
        raw_text: Full resume text
        experience_blocks: Experience section blocks
        nlp: Loaded spaCy model

    Returns:
        Dictionary of advanced signals
    """
    signals = {}

    # Process full text
    doc = nlp(raw_text)

    # --- 1. Context-aware first-person detection ---
    first_person_count = 0
    for token in doc:
        # Check if token is first-person pronoun AND is subject
        if (token.pos_ == "PRON" and
                token.text.lower() in _FIRST_PERSON_VERBS):
            # Only count if it's actually the subject of a verb
            if token.dep_ in {"nsubj", "nsubjpass"}:
                first_person_count += 1

    signals["first_person_count"] = first_person_count
    signals["uses_first_person"] = first_person_count >= 2

    # First-person specifically in experience (red flag)
    experience_text = "\n".join(block.get("text", "")
                                for block in experience_blocks)
    if experience_text:
        exp_doc = nlp(experience_text)
        exp_first_person = sum(
            1 for token in exp_doc
            if token.pos_ == "PRON"
            and token.text.lower() in _FIRST_PERSON_VERBS
            and token.dep_ in {"nsubj", "nsubjpass"}
        )
        signals["uses_first_person_in_experience"] = exp_first_person >= 2
    else:
        signals["uses_first_person_in_experience"] = False

    # --- 2. Passive voice detection ---
    passive_count = 0
    for token in doc:
        # Passive voice: auxiliary passive + past participle
        if token.dep_ == "auxpass":
            passive_count += 1

    signals["passive_voice_count"] = passive_count
    signals["uses_passive_voice"] = passive_count >= 3

    # --- 3. Action verb detection ---
    ACTION_VERBS = _ACTION_VERBS

    action_verb_count = 0
    for token in doc:
        if (token.pos_ == "VERB" and
                token.lemma_.lower() in ACTION_VERBS):
            # Bonus: Check if verb starts a bullet/sentence (stronger signal)
            if token.i == 0 or doc[token.i - 1].is_punct:
                action_verb_count += 1

    signals["action_verb_count"] = action_verb_count
    signals["has_action_verbs"] = action_verb_count >= 3

    # --- 4. Sentence quality ---
    sentences = list(doc.sents)
    if sentences:
        avg_sentence_length = sum(len(sent)
                                  for sent in sentences) / len(sentences)
        signals["avg_sentence_length"] = round(avg_sentence_length, 1)
        signals["has_long_sentences"] = avg_sentence_length > 25
    else:
        signals["avg_sentence_length"] = 0.0
        signals["has_long_sentences"] = False

    # --- 5. Vocabulary richness ---
    unique_words = len(set(
        token.text.lower() for token in doc
        if token.is_alpha and not token.is_stop
    ))
    total_words = len([token for token in doc if token.is_alpha])

    if total_words > 0:
        lexical_diversity = unique_words / total_words
        signals["lexical_diversity"] = round(lexical_diversity, 3)
        signals["is_repetitive"] = lexical_diversity < 0.4
    else:
        signals["lexical_diversity"] = 0.0
        signals["is_repetitive"] = False

    return signals


# ============================================================
# FALLBACK / DUMMY SIGNALS
# ============================================================

def _get_dummy_advanced_signals() -> Dict[str, Any]:
    """
    Return dummy values for advanced signals when spaCy unavailable.
    These act as 'unknown' placeholders.
    """
    return {
        # First-person (use basic regex version as fallback)
        "first_person_count": 0,
        "uses_first_person": False,  # Will use basic version
        "uses_first_person_in_experience": False,

        # Passive voice (unknown)
        "passive_voice_count": 0,
        "uses_passive_voice": False,

        # Action verbs (unknown)
        "action_verb_count": 0,
        "has_action_verbs": False,

        # Sentence quality (unknown)
        "avg_sentence_length": 0.0,
        "has_long_sentences": False,

        # Vocabulary (unknown)
        "lexical_diversity": 0.0,
        "is_repetitive": False,
    }


# ============================================================
# V2 PLACEHOLDERS (Future implementation)
# ============================================================

def _compute_metric_density(text: str) -> float:
    """
    TODO v2: Calculate metrics per 100 words.
    Pattern: %, $, numbers with units (50%, $1M, 10K users)
    """
    # METRIC_REGEX = re.compile(r'(\d+%|\$\d+[KMB]?|\d+[KMB]?\s*(users|customers|revenue))', re.I)
    raise NotImplementedError("v2 feature - metric density")


def _check_bullet_consistency(blocks: list) -> bool:
    """
    TODO v2: Check if bullets use consistent formatting.
    Analyze: •, -, *, or numbered (1., 2., 3.)
    """
    raise NotImplementedError("v2 feature - bullet consistency")


def _count_dates_in_blocks(blocks_list: list) -> int:
    """Count total year mentions across all blocks."""
    count = 0
    for block in blocks_list:
        matches = YEAR_REGEX.findall(block.get("text", ""))
        count += len(matches)
    return count


def _detect_first_person_usage(text: str) -> dict:
    """
    Detect first-person pronouns with context.
    Returns counts and whether it's likely inappropriate.
    """
    # Match first-person pronouns
    matches = FIRST_PERSON_REGEX.findall(text)
    count = len(matches)

    # Context check: First person is OK in summary, bad in experience
    return {
        "count": count,
        "uses_first_person": count >= 2,  # Threshold: 2+ occurrences
    }


def _get_nlp():
    '''
    lazy laoding spacy model, graceful degradation if spacy not avilable
    '''
    global _nlp_model
    if _nlp_model is None:
        # TODO: replace these prints with emit events
        try:
            import spacy
            _nlp_model = spacy.load("en_core_web_sm")
            print("[SIGNALS] spaCy model loaded successfully")
        except (ImportError, OSError) as e:
            print(f"[SIGNALS] spaCy not available: {e}")
            print("[SIGNALS] Falling back to regex-only analysis")
            _nlp_model = False
    return _nlp_model if _nlp_model is not False else None
