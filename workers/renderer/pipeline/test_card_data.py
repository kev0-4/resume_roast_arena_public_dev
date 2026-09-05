import pytest

from workers.renderer.pipeline.card_data import (
    compute_score,
    compute_stamp,
    build_card_context,
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
