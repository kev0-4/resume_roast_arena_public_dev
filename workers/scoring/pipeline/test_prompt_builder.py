"""
Unit tests for workers/scoring/pipeline/prompt_builder.py

Run with:  python -m pytest workers/scoring/pipeline/test_prompt_builder.py -v
"""

import pytest
from .prompt_builder import (
    normalize_placeholders,
    build_roast_prompt,
    _format_issues,
    _format_strengths,
    _format_resume_sections,
    _section_text,
)
from ..schemas import ScoringResult, Issue, Strength, Severity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_block(text: str, start: int = 0, end: int = None) -> dict:
    end = end or start + len(text)
    return {"text": text, "source_span": {"start": start, "end": end}}


def _make_anonymized(blocks: dict, metrics: dict = None) -> dict:
    return {
        "session_id": "test-session",
        "anonymization_version": "1.0",
        "content": {"blocks": blocks},
        "redactions": {"emails": [], "phones": [], "urls": []},
        "signals": {},
        "metrics": metrics or {"word_count": 250},
        "timestamps": {
            "normalized_at": "2024-01-01T00:00:00",
            "anonymized_at": "2024-01-01T00:01:00",
        },
    }


def _make_scoring_result(issues=None, strengths=None) -> ScoringResult:
    return ScoringResult(
        issues=issues or [],
        strengths=strengths or [],
    )


# ---------------------------------------------------------------------------
# normalize_placeholders
# ---------------------------------------------------------------------------

class TestNormalizePlaceholders:
    def test_single_email(self):
        assert normalize_placeholders("reach me at {{EMAIL_1}}") == "reach me at [EMAIL]"

    def test_single_phone(self):
        assert normalize_placeholders("call {{PHONE_1}}") == "call [PHONE]"

    def test_single_url(self):
        assert normalize_placeholders("see {{URL_1}}") == "see [URL]"

    def test_multiple_same_type(self):
        result = normalize_placeholders("{{EMAIL_1}} and {{EMAIL_2}}")
        assert result == "[EMAIL] and [EMAIL]"

    def test_multiple_different_types(self):
        result = normalize_placeholders("{{EMAIL_1}} / {{PHONE_1}} / {{URL_1}}")
        assert result == "[EMAIL] / [PHONE] / [URL]"

    def test_no_placeholders(self):
        text = "No placeholders here, just plain text."
        assert normalize_placeholders(text) == text

    def test_empty_string(self):
        assert normalize_placeholders("") == ""

    def test_preserves_surrounding_text(self):
        result = normalize_placeholders("Email: {{EMAIL_1}}. Phone: {{PHONE_1}}.")
        assert result == "Email: [EMAIL]. Phone: [PHONE]."

    def test_high_numbered_placeholder(self):
        assert normalize_placeholders("{{URL_99}}") == "[URL]"


# ---------------------------------------------------------------------------
# _section_text
# ---------------------------------------------------------------------------

class TestSectionText:
    def test_single_block(self):
        blocks = [_make_block("Software engineer with 5 years experience.")]
        assert _section_text(blocks) == "Software engineer with 5 years experience."

    def test_multiple_blocks_joined(self):
        blocks = [_make_block("Line one."), _make_block("Line two.")]
        result = _section_text(blocks)
        assert "Line one." in result
        assert "Line two." in result

    def test_placeholder_normalized(self):
        blocks = [_make_block("Contact: {{EMAIL_1}}")]
        assert _section_text(blocks) == "Contact: [EMAIL]"

    def test_empty_block_list(self):
        assert _section_text([]) == ""

    def test_blocks_with_empty_text_skipped(self):
        blocks = [_make_block(""), _make_block("   "), _make_block("Real content.")]
        assert _section_text(blocks) == "Real content."

    def test_non_dict_blocks_skipped(self):
        blocks = [None, "bad", _make_block("Good block.")]
        assert _section_text(blocks) == "Good block."


# ---------------------------------------------------------------------------
# _format_resume_sections
# ---------------------------------------------------------------------------

class TestFormatResumeSections:
    def test_known_sections_appear_with_labels(self):
        blocks = {
            "experience": [_make_block("Engineer at Acme.")],
            "education": [_make_block("B.Sc. Computer Science.")],
        }
        result = _format_resume_sections(blocks)
        assert "[WORK EXPERIENCE]" in result
        assert "[EDUCATION]" in result
        assert "Engineer at Acme." in result

    def test_section_order_respected(self):
        blocks = {
            "education": [_make_block("B.Sc.")],
            "summary": [_make_block("Driven developer.")],
            "experience": [_make_block("3 years.")],
        }
        result = _format_resume_sections(blocks)
        # summary should appear before experience, experience before education
        assert result.index("[SUMMARY") < result.index("[WORK EXPERIENCE]")
        assert result.index("[WORK EXPERIENCE]") < result.index("[EDUCATION]")

    def test_unknown_section_appended(self):
        blocks = {
            "awards": [_make_block("Best Employee 2023.")],
        }
        result = _format_resume_sections(blocks)
        assert "[AWARDS]" in result
        assert "Best Employee 2023." in result

    def test_empty_blocks_dict(self):
        result = _format_resume_sections({})
        assert "(no content extracted)" in result

    def test_sections_with_empty_text_omitted(self):
        blocks = {
            "summary": [_make_block("")],
            "experience": [_make_block("Real work.")],
        }
        result = _format_resume_sections(blocks)
        assert "[SUMMARY" not in result
        assert "[WORK EXPERIENCE]" in result


# ---------------------------------------------------------------------------
# _format_issues
# ---------------------------------------------------------------------------

class TestFormatIssues:
    def test_empty_issues(self):
        assert _format_issues([]) == "None detected."

    def test_critical_first(self):
        issues = [
            Issue(code="A", message="Low severity", severity=Severity.LOW),
            Issue(code="B", message="Critical problem", severity=Severity.CRITICAL),
        ]
        result = _format_issues(issues)
        assert result.index("[CRITICAL]") < result.index("[LOW]")

    def test_severity_order_full(self):
        issues = [
            Issue(code="D", message="Low", severity=Severity.LOW),
            Issue(code="C", message="Medium", severity=Severity.MEDIUM),
            Issue(code="B", message="High", severity=Severity.HIGH),
            Issue(code="A", message="Critical", severity=Severity.CRITICAL),
        ]
        result = _format_issues(issues)
        assert result.index("[CRITICAL]") < result.index("[HIGH]")
        assert result.index("[HIGH]") < result.index("[MEDIUM]")
        assert result.index("[MEDIUM]") < result.index("[LOW]")

    def test_issue_message_present(self):
        issues = [Issue(code="X", message="Missing summary section", severity=Severity.LOW)]
        assert "Missing summary section" in _format_issues(issues)


# ---------------------------------------------------------------------------
# _format_strengths
# ---------------------------------------------------------------------------

class TestFormatStrengths:
    def test_empty_strengths(self):
        assert _format_strengths([]) == "None detected."

    def test_strength_message_present(self):
        strengths = [Strength(code="S1", message="Good vocabulary diversity")]
        assert "Good vocabulary diversity" in _format_strengths(strengths)

    def test_multiple_strengths(self):
        strengths = [
            Strength(code="S1", message="Has experience section"),
            Strength(code="S2", message="Includes project experience"),
        ]
        result = _format_strengths(strengths)
        assert "Has experience section" in result
        assert "Includes project experience" in result


# ---------------------------------------------------------------------------
# build_roast_prompt (integration)
# ---------------------------------------------------------------------------

class TestBuildRoastPrompt:
    def test_returns_string(self):
        anonymized = _make_anonymized(
            blocks={"experience": [_make_block("Engineer at Acme.")]}
        )
        result = _make_scoring_result()
        prompt = build_roast_prompt(anonymized=anonymized, scoring_result=result)
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_prompt_contains_resume_content(self):
        anonymized = _make_anonymized(
            blocks={"experience": [_make_block("Senior engineer at BigCorp.")]}
        )
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "Senior engineer at BigCorp." in prompt

    def test_placeholders_converted_in_prompt(self):
        anonymized = _make_anonymized(
            blocks={"experience": [_make_block("Email: {{EMAIL_1}}")]}
        )
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "{{EMAIL_1}}" not in prompt
        assert "[EMAIL]" in prompt

    def test_issues_appear_in_prompt(self):
        anonymized = _make_anonymized(blocks={})
        scoring_result = _make_scoring_result(
            issues=[Issue(code="NO_SUMMARY", message="Missing summary section", severity=Severity.LOW)]
        )
        prompt = build_roast_prompt(anonymized=anonymized, scoring_result=scoring_result)
        assert "Missing summary section" in prompt

    def test_strengths_appear_in_prompt(self):
        anonymized = _make_anonymized(blocks={})
        scoring_result = _make_scoring_result(
            strengths=[Strength(code="HAS_EXP", message="Includes experience section")]
        )
        prompt = build_roast_prompt(anonymized=anonymized, scoring_result=scoring_result)
        assert "Includes experience section" in prompt

    def test_word_count_in_prompt(self):
        anonymized = _make_anonymized(blocks={}, metrics={"word_count": 312})
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "312" in prompt

    def test_prompt_contains_output_format_labels(self):
        anonymized = _make_anonymized(blocks={})
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "VERDICT:" in prompt
        assert "ROAST:" in prompt
        assert "FIXES:" in prompt

    def test_raises_on_missing_content(self):
        bad_anonymized = {"session_id": "x", "metrics": {}}
        with pytest.raises(ValueError, match="missing 'content'"):
            build_roast_prompt(
                anonymized=bad_anonymized,
                scoring_result=_make_scoring_result(),
            )

    def test_raises_on_bad_blocks_type(self):
        bad_anonymized = {"content": {"blocks": "not-a-dict"}, "metrics": {}}
        with pytest.raises(ValueError, match="not a dict"):
            build_roast_prompt(
                anonymized=bad_anonymized,
                scoring_result=_make_scoring_result(),
            )

    def test_empty_blocks_handled_gracefully(self):
        anonymized = _make_anonymized(blocks={})
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "no content extracted" in prompt

    def test_no_raw_pii_instruction_in_prompt(self):
        """Verify the prompt instructs the LLM not to reveal PII."""
        anonymized = _make_anonymized(blocks={})
        prompt = build_roast_prompt(
            anonymized=anonymized,
            scoring_result=_make_scoring_result(),
        )
        assert "PII" in prompt or "real name" in prompt
