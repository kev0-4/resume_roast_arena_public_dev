from workers.renderer.pipeline.card_data import (
    compute_score,
    compute_stamp,
    structural_deduction,
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


class TestStructuralDeduction:
    def test_no_issues_costs_nothing(self):
        assert structural_deduction(_summary()) == 0

    def test_severity_weights(self):
        assert structural_deduction(_summary(critical_issues=1)) == 20
        assert structural_deduction(_summary(high_issues=1)) == 10
        assert structural_deduction(_summary(medium_issues=1)) == 5
        assert structural_deduction(_summary(low_issues=1)) == 2

    def test_mixed_severities_sum(self):
        assert structural_deduction(
            _summary(critical_issues=1, high_issues=1, medium_issues=1, low_issues=1)
        ) == 20 + 10 + 5 + 2

    def test_missing_keys_default_to_zero(self):
        assert structural_deduction({}) == 0


class TestComputeScore:
    def test_substance_score_is_the_baseline(self):
        # No structural issues -> the score is exactly the LLM's judgment.
        assert compute_score(_summary(), substance_score=72) == 72

    def test_structural_issues_deduct_from_the_substance_baseline(self):
        assert compute_score(_summary(high_issues=1), substance_score=72) == 62

    def test_content_free_resume_scores_low_even_with_clean_structure(self):
        # The whole point of the change: a resume with every section
        # present but hollow writing must not score near 100. Under the
        # old flag-deduction design this floored around 68.
        assert compute_score(_summary(total_strengths=3), substance_score=8) == 8

    def test_missing_substance_score_falls_back_to_structural_only(self):
        # roast.json predating substance_score -- scored as if content
        # were neutral, not worthless.
        assert compute_score(_summary(high_issues=1)) == 90
        assert compute_score(_summary()) == 100

    def test_clamps_to_zero_rather_than_going_negative(self):
        assert compute_score(_summary(critical_issues=5), substance_score=40) == 0

    def test_never_exceeds_100(self):
        assert compute_score(_summary(), substance_score=100) == 100

    def test_out_of_range_substance_score_is_clamped(self):
        assert compute_score(_summary(), substance_score=150) == 100
        assert compute_score(_summary(), substance_score=-30) == 0

    def test_missing_summary_keys_default_to_zero(self):
        assert compute_score({}, substance_score=55) == 55


class TestComputeStamp:
    def test_high_score_is_solid(self):
        assert compute_stamp(92) == "SOLID"

    def test_exactly_at_solid_threshold_is_solid(self):
        assert compute_stamp(85) == "SOLID"

    def test_just_below_solid_threshold_is_mid(self):
        assert compute_stamp(84) == "MID"

    def test_exactly_at_mid_threshold_is_mid(self):
        assert compute_stamp(60) == "MID"

    def test_just_below_mid_threshold_is_roasted(self):
        assert compute_stamp(59) == "ROASTED"

    def test_zero_is_roasted(self):
        assert compute_stamp(0) == "ROASTED"


class TestBuildCardContext:
    def test_assembles_expected_fields(self):
        scored = {
            "summary": _summary(critical_issues=1, total_issues=3, total_strengths=1),
        }
        roast = {
            "verdict": "This resume screams for help.",
            "substance_score": 45,
            "quality_flags": [],
        }

        context = build_card_context(scored=scored, roast=roast, display_name="SavageIntern4821")

        assert context["candidate_name"] == "SavageIntern4821"
        assert context["punchline"] == "This resume screams for help."
        assert context["score"] == 25  # 45 substance - 20 for the critical
        assert context["stamp"] == "ROASTED"
        assert context["stat2_label"] == "Issues Found"
        assert context["stat2_value"] == "3"
        assert isinstance(context["resume_lines"], list) and context["resume_lines"]
        assert context["cta_text"]

    def test_stamp_always_agrees_with_the_score_beside_it(self):
        # These two are rendered next to each other on the card, so they
        # must never contradict. The previous design derived the stamp
        # from issue counts and the score from something else, which let a
        # content-free resume render "SOLID" beside a single-digit score.
        scored = {"summary": _summary(total_strengths=3)}  # zero structural issues
        for substance, expected in [(95, "SOLID"), (70, "MID"), (10, "ROASTED")]:
            context = build_card_context(
                scored=scored,
                roast={"verdict": "v", "substance_score": substance},
                display_name="A",
            )
            assert context["score"] == substance
            assert context["stamp"] == expected

    def test_substance_score_separates_strong_from_hollow_content(self):
        # The gap this feature exists to close: the rule engine sees both
        # of these as flawless, but only one describes real work.
        scored = {"summary": _summary(total_strengths=3)}

        strong = build_card_context(
            scored=scored, roast={"verdict": "v", "substance_score": 93}, display_name="A"
        )
        hollow = build_card_context(
            scored=scored, roast={"verdict": "v", "substance_score": 12}, display_name="A"
        )

        assert strong["score"] - hollow["score"] > 50
        assert strong["stamp"] == "SOLID"
        assert hollow["stamp"] == "ROASTED"

    def test_quality_flags_are_counted_as_issues_but_do_not_move_the_score(self):
        scored = {"summary": _summary(total_issues=2, high_issues=2)}
        base_roast = {"verdict": "v", "substance_score": 70}
        flagged_roast = {
            "verdict": "v",
            "substance_score": 70,
            "quality_flags": ["GENERIC_BULLETS", "BUZZWORD_FILLER"],
        }

        base = build_card_context(scored=scored, roast=base_roast, display_name="A")
        flagged = build_card_context(scored=scored, roast=flagged_roast, display_name="A")

        assert base["score"] == flagged["score"] == 50
        assert base["stat2_value"] == "2"
        assert flagged["stat2_value"] == "4"

    def test_roast_without_substance_score_still_renders(self):
        # Legacy roast.json -- must not KeyError.
        scored = {"summary": _summary(high_issues=1, total_issues=1)}
        context = build_card_context(
            scored=scored, roast={"verdict": "v"}, display_name="A"
        )
        assert context["score"] == 90
        assert context["stamp"] == "SOLID"
