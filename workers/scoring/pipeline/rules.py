"""
workers/scoring/pipeline/rules.py
Scoring rules.

Convert signals + metrics → issues & strengths.
Pure deterministic logic. No side effects.
"""

from typing import Dict, Any, List

from ..schemas import Issue, Strength, Severity


# ------------------------------------------------------------
# MAIN ENTRYPOINT
# ------------------------------------------------------------
def evaluate_rules(
    *,
    signals: Dict[str, Any],
    metrics: Dict[str, Any],
    blocks: Dict[str, list],
) -> tuple[List[Issue], List[Strength]]:

    issues: List[Issue] = []
    strengths: List[Strength] = []

    # ------------------------------------------------------------
    # SECTION PRESENCE RULES
    # ------------------------------------------------------------
    if not signals.get("has_experience"):
        issues.append(Issue(
            code="NO_EXPERIENCE",
            message="No experience section found",
            severity=Severity.CRITICAL,
        ))
    else:
        strengths.append(Strength(
            code="HAS_EXPERIENCE",
            message="Includes experience section",
        ))

    if not signals.get("has_projects"):
        issues.append(Issue(
            code="NO_PROJECTS",
            message="No projects section found",
            severity=Severity.HIGH,
        ))
    else:
        strengths.append(Strength(
            code="HAS_PROJECTS",
            message="Includes project experience",
        ))

    if not signals.get("has_summary"):
        issues.append(Issue(
            code="NO_SUMMARY",
            message="Missing summary section",
            severity=Severity.LOW,
        ))
    else:
        strengths.append(Strength(
            code="HAS_SUMMARY",
            message="Includes summary section",
        ))

    # ------------------------------------------------------------
    # CONTACT RULES
    # ------------------------------------------------------------
    if not signals.get("has_contact_info"):
        issues.append(Issue(
            code="NO_CONTACT_INFO",
            message="Missing contact information",
            severity=Severity.CRITICAL,
        ))

    if not signals.get("has_professional_links"):
        issues.append(Issue(
            code="NO_PROFESSIONAL_LINKS",
            message="No LinkedIn/GitHub/portfolio links found",
            severity=Severity.MEDIUM,
        ))

    # ------------------------------------------------------------
    # EXPERIENCE QUALITY
    # ------------------------------------------------------------
    if not signals.get("has_dates_in_experience"):
        issues.append(Issue(
            code="NO_DATES_IN_EXPERIENCE",
            message="Experience section lacks clear dates",
            severity=Severity.HIGH,
        ))

    # ------------------------------------------------------------
    # WRITING QUALITY
    # ------------------------------------------------------------
    if signals.get("uses_first_person_basic"):
        issues.append(Issue(
            code="FIRST_PERSON_USAGE",
            message="Uses first-person language (avoid 'I', 'me')",
            severity=Severity.MEDIUM,
        ))

    # ------------------------------------------------------------
    # LENGTH RULES (metrics-driven)
    # ------------------------------------------------------------
    word_count = metrics.get("word_count", 0)

    if word_count < 150:
        issues.append(Issue(
            code="RESUME_TOO_SHORT",
            message="Resume is too short",
            severity=Severity.HIGH,
        ))

    if word_count > 1200:
        issues.append(Issue(
            code="RESUME_TOO_LONG",
            message="Resume is too long",
            severity=Severity.MEDIUM,
        ))

    # ------------------------------------------------------------
    # SENTENCE QUALITY
    # ------------------------------------------------------------
    avg_sentence_length = metrics.get("avg_sentence_length", 0)

    if avg_sentence_length > 30:
        issues.append(Issue(
            code="LONG_SENTENCES",
            message="Sentences are too long and hard to read",
            severity=Severity.MEDIUM,
        ))

    # ------------------------------------------------------------
    # VOCABULARY
    # ------------------------------------------------------------
    lexical_diversity = metrics.get("lexical_diversity", 0)

    if lexical_diversity < 0.4:
        issues.append(Issue(
            code="LOW_VOCABULARY_VARIETY",
            message="Vocabulary is repetitive",
            severity=Severity.LOW,
        ))
    else:
        strengths.append(Strength(
            code="GOOD_VOCABULARY",
            message="Good vocabulary diversity",
        ))

    # ------------------------------------------------------------
    # NLP-BASED RULES (only if analysis ran successfully)
    # ------------------------------------------------------------
    if signals.get("nlp_analysis_successful"):
        if signals.get("uses_passive_voice"):
            issues.append(Issue(
                code="PASSIVE_VOICE",
                message="Uses passive voice in experience descriptions",
                severity=Severity.MEDIUM,
            ))

        if not signals.get("has_action_verbs"):
            issues.append(Issue(
                code="NO_ACTION_VERBS",
                message="Experience bullets lack strong action verbs",
                severity=Severity.HIGH,
            ))

    # ------------------------------------------------------------
    # SIGNAL-BASED STRENGTHS
    # ------------------------------------------------------------
    if signals.get("has_links"):
        strengths.append(Strength(
            code="HAS_LINKS",
            message="Includes external links",
        ))

    if signals.get("has_skills"):
        strengths.append(Strength(
            code="HAS_SKILLS",
            message="Includes skills section",
        ))

    # ------------------------------------------------------------
    # RETURN
    # ------------------------------------------------------------
    return issues, strengths