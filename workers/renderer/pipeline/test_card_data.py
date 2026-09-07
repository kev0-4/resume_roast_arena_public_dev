import pytest

from workers.renderer.pipeline.card_data import (
    compute_score,
    compute_stamp,
    build_card_context,
    merge_quality_into_summary,
)


def _summary(**overrides):
    base = {
        "total_issues": 0,
        "critical_issues": 0,
        "high_issues": 0,
        "medium_issues": 0,
        "low_issues": 0,
        "total_strengths": 0,
    }
    base.update(overrides)
    return base


class TestComputeScore:
    def test_no_issues_is_perfect_score(self):
        assert compute_score(_summary()) == 100

    def test_single_critical_issue(self):
        assert compute_score(_summary(critical_issues=1)) == 80

    def test_single_high_issue(self):
        assert compute_score(_summary(high_issues=1)) == 90

    def test_single_medium_issue(self):
        assert compute_score(_summary(medium_issues=1)) == 95

    def test_single_low_issue(self):
        assert compute_score(_summary(low_issues=1)) == 98

    def test_mixed_severities(self):
        assert compute_score(
            _summary(critical_issues=1, high_issues=1, medium_issues=1, low_issues=1)
        ) == 100 - 20 - 10 - 5 - 2

    def test_clamps_to_zero_when_severities_would_go_negative(self):
        assert compute_score(_summary(critical_issues=10)) == 0

    def test_clamps_to_zero_exactly_at_boundary(self):
        # 5 criticals = exactly 100 points off -> 0, not negative
        assert compute_score(_summary(critical_issues=5)) == 0

    def test_never_exceeds_100(self):
        assert compute_score(_summary()) <= 100

    def test_missing_keys_default_to_zero(self):
        assert compute_score({}) == 100


class TestComputeStamp:
    def test_any_critical_issue_is_roasted(self):
        assert compute_stamp(_summary(critical_issues=1)) == "ROASTED"

    def test_two_high_issues_is_roasted(self):
        assert compute_stamp(_summary(high_issues=2)) == "ROASTED"

    def test_one_high_issue_is_not_roasted(self):
        assert compute_stamp(_summary(high_issues=1)) != "ROASTED"

    def test_no_issues_and_several_strengths_is_solid(self):
        assert compute_stamp(_summary(total_issues=0, total_strengths=3)) == "SOLID"

    def test_no_issues_but_few_strengths_is_mid(self):
        assert compute_stamp(_summary(total_issues=0, total_strengths=1)) == "MID"

    def test_some_low_issues_only_is_mid(self):
        assert compute_stamp(_summary(total_issues=2, low_issues=2)) == "MID"

    def test_missing_keys_default_to_mid(self):
        assert compute_stamp({}) == "MID"


class TestMergeQualityIntoSummary:
    def test_no_quality_issues_is_a_no_op(self):
        summary = _summary(high_issues=1, total_issues=1)
        merged = merge_quality_into_summary(summary, [])
        assert merged == summary

    def test_quality_issues_increment_matching_severity_and_total(self):
        summary = _summary(high_issues=1, total_issues=1)
        quality_issues = [
            {"code": "GENERIC_BULLETS", "severity": "high"},
            {"code": "SHALLOW_CONTENT", "severity": "low"},
        ]
        merged = merge_quality_into_summary(summary, quality_issues)
        assert merged["high_issues"] == 2
        assert merged["low_issues"] == 1
        assert merged["total_issues"] == 3

    def test_does_not_mutate_the_original_summary(self):
        summary = _summary(high_issues=1, total_issues=1)
        merge_quality_into_summary(summary, [{"code": "SHALLOW_CONTENT", "severity": "low"}])
        assert summary == _summary(high_issues=1, total_issues=1)

    def test_unknown_severity_key_is_ignored_not_raised(self):
        summary = _summary()
        merged = merge_quality_into_summary(summary, [{"code": "X", "severity": "extreme"}])
        assert merged["total_issues"] == 0


class TestBuildCardContext:
    def test_assembles_expected_fields(self):
        scored = {
            "summary": _summary(critical_issues=1, total_issues=3, total_strengths=1),
        }
        roast = {"verdict": "This resume screams for help."}

        context = build_card_context(scored=scored, roast=roast, display_name="SavageIntern4821")

        assert context["candidate_name"] == "SavageIntern4821"
        assert context["punchline"] == "This resume screams for help."
        assert context["stamp"] == "ROASTED"
        assert context["score"] == 80
        assert context["stat2_label"] == "Issues Found"
        assert context["stat2_value"] == "3"
        assert isinstance(context["resume_lines"], list) and context["resume_lines"]
        assert context["cta_text"]

    def test_quality_issues_pull_the_score_down_below_the_rule_engine_alone(self):
        # This is the whole point of the feature: a resume the rule engine
        # sees as flawless (clean sections, no structural issues) should
        # NOT score 100 if its content is actually generic/hollow -- that
        # was the real gap (see the "why do mediocre resumes score 90+"
        # discussion this feature came out of).
        scored = {"summary": _summary(total_strengths=3)}  # zero rule-engine issues
        roast_clean = {"verdict": "v", "quality_issues": []}
        roast_flagged = {
            "verdict": "v",
            "quality_issues": [
                {"code": "GENERIC_BULLETS", "severity": "high"},
                {"code": "NO_QUANTIFIED_IMPACT", "severity": "high"},
            ],
        }

        clean_context = build_card_context(scored=scored, roast=roast_clean, display_name="A")
        flagged_context = build_card_context(scored=scored, roast=roast_flagged, display_name="A")

        assert clean_context["score"] == 100
        assert clean_context["stamp"] == "SOLID"
        assert flagged_context["score"] == 80
        assert flagged_context["stamp"] == "ROASTED"  # 2 HIGH quality issues trips the same threshold as 2 rule-engine HIGHs
