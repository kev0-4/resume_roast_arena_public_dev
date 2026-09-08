from workers.renderer.pipeline.card_data import (
    MAX_STRUCTURAL_DEDUCTION,
    SOLID_MIN_SCORE,
    MID_MIN_SCORE,
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

    def test_severity_weights_below_the_cap(self):
        assert structural_deduction(_summary(high_issues=1)) == 10
        assert structural_deduction(_summary(medium_issues=1)) == 5
        assert structural_deduction(_summary(low_issues=1)) == 2

    def test_mixed_severities_sum(self):
        assert structural_deduction(_summary(medium_issues=1, low_issues=1)) == 7

    def test_capped_so_structure_cannot_dominate_content(self):
        # Uncapped these weights reach 40-50 on an ordinary resume, enough
        # to drag excellent content below the ROASTED line. Measured: 9 of
        # 15 strong eval resumes stamped ROASTED before the cap.
        assert structural_deduction(_summary(critical_issues=1)) == MAX_STRUCTURAL_DEDUCTION
        assert (
            structural_deduction(
                _summary(critical_issues=3, high_issues=4, medium_issues=2, low_issues=5)
            )
            == MAX_STRUCTURAL_DEDUCTION
        )

    def test_exactly_at_the_cap_is_not_reduced(self):
        # 1 high + 1 low = 12, under the cap; add a medium -> 17, capped.
        assert structural_deduction(_summary(high_issues=1, low_issues=1)) == 12
        assert (
            structural_deduction(_summary(high_issues=1, medium_issues=1, low_issues=1))
            == MAX_STRUCTURAL_DEDUCTION
        )

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
        assert compute_score(_summary(critical_issues=5), substance_score=5) == 0

    def test_structure_alone_cannot_sink_strong_content(self):
        # Every structural rule firing at once still leaves a resume with
        # excellent content well clear of ROASTED.
        wrecked = _summary(critical_issues=3, high_issues=4, medium_issues=3, low_issues=4)
        assert compute_score(wrecked, substance_score=95) == 80
        assert compute_stamp(compute_score(wrecked, substance_score=95)) == "SOLID"

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
        assert compute_stamp(SOLID_MIN_SCORE) == "SOLID"

    def test_just_below_solid_threshold_is_mid(self):
        assert compute_stamp(SOLID_MIN_SCORE - 1) == "MID"

    def test_exactly_at_mid_threshold_is_mid(self):
        assert compute_stamp(MID_MIN_SCORE) == "MID"

    def test_just_below_mid_threshold_is_roasted(self):
        assert compute_stamp(MID_MIN_SCORE - 1) == "ROASTED"

    def test_zero_is_roasted(self):
        assert compute_stamp(0) == "ROASTED"

    def test_thresholds_match_the_measured_composite_distribution(self):
        # Fit to quality-scoring-eval/run_shipped_eval.py over 27 resumes:
        # strong 43-80, mid 20-27, bad 0. The boundary belongs strictly
        # inside the empty band between the strongest mid resume and the
        # weakest strong one, so neither side turns on one example.
        assert 27 < MID_MIN_SCORE < 43
        # SOLID stays hard to earn -- above the strong tier's median (60).
        assert 60 < SOLID_MIN_SCORE <= 80


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
        assert context["score"] == 30  # 45 substance - 15 (capped structural)
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

        assert base["score"] == flagged["score"] == 55  # 70 - 15 (capped)
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
