"""
Tests for the interview planner.

The planner had no tests at all before this file, which is why the repeat
problem below went unnoticed: nothing described what selection was
supposed to do, so nothing could notice it doing the wrong thing.
"""

from . import planner as p
from .catalogue import load_catalogue

CODE_ID = "merge-intervals"
OTHER_CODE_ID = "lru-cache-design"
THIRD_CODE_ID = "rate-limiter-sliding-window"


def _plan(*exercise_ids, vertical="swe", minutes=8):
    rounds = [p.PlannedRound(kind="CONVERSATION", question_id="", minutes=minutes, focus="Resume.")]
    for question_id in exercise_ids:
        rounds.append(
            p.PlannedRound(kind="EXERCISE", question_id=question_id, minutes=99, focus="Because.")
        )
    return p.InterviewPlan(vertical=vertical, rationale="because", rounds=rounds)


def _exercise_ids(plan):
    return [r.question_id for r in plan.rounds if r.kind == "EXERCISE"]


class TestValidatePlan:
    def test_always_starts_with_a_conversation(self):
        out = p.validate_plan(_plan(CODE_ID))
        assert out.rounds[0].kind == "CONVERSATION"
        assert out.rounds[0].question_id == ""

    def test_drops_a_hallucinated_question_id(self):
        out = p.validate_plan(_plan("a-question-that-does-not-exist"))
        assert _exercise_ids(out) == []

    def test_catalogue_timing_overrides_the_model(self):
        out = p.validate_plan(_plan(CODE_ID))
        catalogue_minutes = next(q["minutes"] for q in load_catalogue() if q["id"] == CODE_ID)
        assert out.rounds[1].minutes == catalogue_minutes

    def test_conversation_minutes_are_clamped(self):
        assert p.validate_plan(_plan(minutes=99)).rounds[0].minutes == p.MAX_CONVERSATION_MINUTES
        assert p.validate_plan(_plan(minutes=1)).rounds[0].minutes == p.MIN_CONVERSATION_MINUTES

    def test_caps_the_number_of_exercises(self):
        out = p.validate_plan(_plan(CODE_ID, OTHER_CODE_ID, THIRD_CODE_ID))
        assert len(_exercise_ids(out)) == p.MAX_EXERCISE_ROUNDS

    def test_the_same_question_twice_in_one_plan_is_collapsed(self):
        out = p.validate_plan(_plan(CODE_ID, CODE_ID))
        assert _exercise_ids(out) == [CODE_ID]


class TestNeverRepeatAQuestion:
    """
    The evidence: one real account, eight interviews from ONE resume
    against eight different job descriptions, and lru-cache-design was
    chosen five times. The planner was given the resume and the job
    description and nothing else, so it had no way to know.
    """

    def test_an_already_seen_question_is_dropped(self):
        out = p.validate_plan(_plan(CODE_ID, OTHER_CODE_ID), already_asked=[CODE_ID])
        assert _exercise_ids(out) == [OTHER_CODE_ID]

    def test_enforced_even_when_the_model_ignores_the_prompt(self):
        # The seen question is not in the prompt's catalogue at all, so a
        # plan naming it means the model ignored the list. validate_plan is
        # what makes the rule true rather than merely requested.
        out = p.validate_plan(
            _plan(CODE_ID, OTHER_CODE_ID, THIRD_CODE_ID), already_asked=[CODE_ID]
        )
        assert CODE_ID not in _exercise_ids(out)
        assert _exercise_ids(out) == [OTHER_CODE_ID, THIRD_CODE_ID]

    def test_an_unseen_question_is_untouched(self):
        out = p.validate_plan(_plan(CODE_ID), already_asked=[OTHER_CODE_ID])
        assert _exercise_ids(out) == [CODE_ID]

    def test_a_first_time_candidate_is_unaffected(self):
        assert p.validate_plan(_plan(CODE_ID, OTHER_CODE_ID)) == p.validate_plan(
            _plan(CODE_ID, OTHER_CODE_ID), already_asked=[]
        )

    def test_exhausted_candidate_still_gets_one_exercise(self):
        # A repeat beats an empty round: they came here to be interviewed.
        out = p.validate_plan(_plan(CODE_ID, OTHER_CODE_ID), already_asked=[CODE_ID, OTHER_CODE_ID])
        assert len(_exercise_ids(out)) == 1

    def test_the_repeat_is_the_least_recently_seen(self):
        # already_asked is oldest first, so CODE_ID is the stalest.
        out = p.validate_plan(_plan(OTHER_CODE_ID, CODE_ID), already_asked=[CODE_ID, OTHER_CODE_ID])
        assert _exercise_ids(out) == [CODE_ID]

    def test_only_one_repeat_is_allowed_back(self):
        out = p.validate_plan(_plan(CODE_ID, OTHER_CODE_ID), already_asked=[OTHER_CODE_ID, CODE_ID])
        assert len(_exercise_ids(out)) == 1

    def test_a_conversation_only_plan_is_not_given_a_repeat(self):
        # The planner deliberately chose no exercise -- for an HR or IB
        # candidate that is the right answer, and inventing one would put a
        # code editor in front of someone who should never see one.
        out = p.validate_plan(_plan(), already_asked=[CODE_ID])
        assert _exercise_ids(out) == []


class TestPlanningPrompt:
    def test_lists_the_catalogue(self):
        prompt = p.build_planning_prompt("RESUME", "JD")
        assert CODE_ID in prompt

    def test_seen_questions_are_removed_from_the_list(self):
        # Removed rather than listed-and-forbidden: naming them would put
        # the exact ids we do not want straight back in front of the model.
        prompt = p.build_planning_prompt("RESUME", "JD", already_asked=[CODE_ID])
        assert CODE_ID not in prompt
        assert OTHER_CODE_ID in prompt

    def test_survives_a_candidate_who_has_seen_everything(self):
        every_id = [q["id"] for q in load_catalogue()]
        prompt = p.build_planning_prompt("RESUME", "JD", already_asked=every_id)
        assert "no unseen questions remain" in prompt

    def test_includes_the_resume_and_job_description(self):
        prompt = p.build_planning_prompt("RESUME-MARKER", "JD-MARKER")
        assert "RESUME-MARKER" in prompt
        assert "JD-MARKER" in prompt


class TestConversationOnlyFallback:
    def test_is_a_complete_runnable_plan(self):
        plan = p.conversation_only_plan("planner unavailable")
        assert len(plan.rounds) == 1
        assert plan.rounds[0].kind == "CONVERSATION"
        assert plan.vertical == "unknown"
