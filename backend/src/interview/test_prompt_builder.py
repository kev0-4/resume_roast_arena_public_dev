import pytest

from . import prompt_builder as pb


def _anonymized(blocks=None):
    return {"content": {"blocks": blocks or {"experience": [{"text": "Built a caching layer."}]}}}


def _roast(**overrides):
    defaults = dict(
        verdict="Competent but forgettable.",
        roast="The experience section is fine, but nothing here sticks.",
        fixes=["Quantify your impact.", "Cut the buzzwords."],
        highlights=[{"quote": "team player", "comment": "Everyone says this."}],
        quality_flags=["GENERIC_BULLETS"],
    )
    defaults.update(overrides)
    return defaults


class TestNormalizePlaceholders:
    def test_converts_bracket_placeholder(self):
        assert pb.normalize_placeholders("Contact: {{EMAIL_1}}") == "Contact: [EMAIL_1]"

    def test_multiple_placeholders(self):
        assert pb.normalize_placeholders("{{EMAIL_1}} {{PHONE_2}}") == "[EMAIL_1] [PHONE_2]"

    def test_no_placeholders_unchanged(self):
        assert pb.normalize_placeholders("plain text") == "plain text"


class TestFormatResumeSections:
    def test_known_section_gets_labeled(self):
        text = pb._format_resume_sections({"experience": [{"text": "Built X."}]})
        assert "[WORK EXPERIENCE]" in text
        assert "Built X." in text

    def test_unknown_section_appended_uppercased(self):
        text = pb._format_resume_sections({"volunteering": [{"text": "Helped out."}]})
        assert "[VOLUNTEERING]" in text

    def test_empty_blocks_returns_placeholder_text(self):
        assert pb._format_resume_sections({}) == "(no content extracted)"

    def test_section_order_respected(self):
        text = pb._format_resume_sections(
            {"skills": [{"text": "Python"}], "summary": [{"text": "A summary."}]}
        )
        assert text.index("[SUMMARY") < text.index("[SKILLS")


class TestBuildInterviewSystemContext:
    def test_raises_on_missing_content(self):
        with pytest.raises(ValueError):
            pb.build_interview_system_context({}, _roast(), "Some JD")

    def test_raises_on_bad_blocks_type(self):
        with pytest.raises(ValueError):
            pb.build_interview_system_context({"content": {"blocks": "not a dict"}}, _roast(), "Some JD")

    def test_includes_job_description(self):
        ctx = pb.build_interview_system_context(_anonymized(), _roast(), "Senior Backend Engineer role")
        assert "Senior Backend Engineer role" in ctx

    def test_includes_roast_verdict_and_fixes(self):
        ctx = pb.build_interview_system_context(_anonymized(), _roast(), "JD text")
        assert "Competent but forgettable." in ctx
        assert "Quantify your impact." in ctx

    def test_includes_highlights(self):
        ctx = pb.build_interview_system_context(_anonymized(), _roast(), "JD text")
        assert "team player" in ctx

    def test_missing_roast_fields_do_not_crash(self):
        ctx = pb.build_interview_system_context(_anonymized(), {}, "JD text")
        assert "None recorded." in ctx


class TestBuildLiveSystemInstruction:
    def test_wraps_the_shared_context(self):
        ctx = pb.build_interview_system_context(_anonymized(), _roast(), "JD text")
        instruction = pb.build_live_system_instruction(ctx)
        assert ctx in instruction

    def test_tells_the_model_to_speak_first(self):
        # Without this the model waits for the candidate, the candidate
        # waits for the model, and the interview opens in silence.
        instruction = pb.build_live_system_instruction("CTX")
        assert "Open the interview yourself" in instruction

    def test_tells_the_model_it_can_be_interrupted(self):
        instruction = pb.build_live_system_instruction("CTX")
        assert "interrupt" in instruction.lower()


class TestBuildScoringPrompt:
    def test_renders_speaker_tagged_utterances(self):
        utterances = [
            {"speaker": "interviewer", "text": "Tell me about X."},
            {"speaker": "candidate", "text": "I did X."},
        ]
        prompt = pb.build_scoring_prompt("CTX", utterances)
        assert "INTERVIEWER: Tell me about X." in prompt
        assert "CANDIDATE: I did X." in prompt

    def test_includes_the_system_context(self):
        prompt = pb.build_scoring_prompt("CTX-MARKER", [])
        assert "CTX-MARKER" in prompt

    def test_skips_blank_utterances(self):
        prompt = pb.build_scoring_prompt("CTX", [{"speaker": "candidate", "text": "   "}])
        assert "CANDIDATE:" not in prompt

    def test_empty_transcript_handled(self):
        prompt = pb.build_scoring_prompt("CTX", [])
        assert "nothing was said" in prompt

    def test_includes_score_range(self):
        prompt = pb.build_scoring_prompt("CTX", [])
        assert "1" in prompt and "10" in prompt

    def test_one_skip_is_a_dent_not_a_disqualification(self):
        prompt = pb.build_scoring_prompt("CTX", [], skipped_questions=1)
        assert "declined to answer 1 question" in prompt
        assert "not a disqualification" in prompt

    def test_repeated_skips_weigh_heavily(self):
        prompt = pb.build_scoring_prompt("CTX", [], skipped_questions=4)
        assert "declined to answer 4 questions" in prompt
        assert "weigh heavily against the score" in prompt

    def test_clean_run_gets_no_conduct_block(self):
        prompt = pb.build_scoring_prompt("CTX", [], skipped_questions=0)
        assert "HOW THE CANDIDATE CONDUCTED THEMSELVES" not in prompt

    def test_time_wasting_end_scores_near_the_bottom(self):
        prompt = pb.build_scoring_prompt(
            "CTX", [], ended_early={"reason": "Kept asking about lasagna.", "category": "TIME_WASTING"}
        )
        assert "near the bottom of the range" in prompt
        assert "Kept asking about lasagna." in prompt

    def test_a_complete_interview_ending_early_is_not_penalised(self):
        prompt = pb.build_scoring_prompt(
            "CTX", [], ended_early={"reason": "Covered enough ground.", "category": "COMPLETE"}
        )
        assert "is NOT itself a negative" in prompt


def _exercise(**overrides):
    result = {
        "index": 1,
        "question_id": "lru-cache-design",
        "format": "CODE",
        "language": "python",
        "submission": "class LRUCache: ...",
        "seconds_taken": 554,
        "pasted": False,
        "runs": 3,
        "failed_runs": 1,
        "cases": {
            "visible_passed": 4,
            "visible_total": 4,
            "hidden_passed": 1,
            "hidden_total": 2,
            "failed_hidden": ["reinsert-existing-key"],
        },
        "conduct": "Took 9 minutes. Ran the code 3 times.",
        "review": {
            "correct": False,
            "complexity": "O(1)",
            "strengths": ["Correct doubly-linked list."],
            "problems": ["Re-inserting an existing key leaves a stale node."],
            "interviewer_notes": "Ask what happens on a repeated put.",
            "score": 8,
        },
    }
    result.update(overrides)
    return result


class TestExerciseRoundsInScoring:
    """
    The gap these cover: a candidate scored 10/10 on a coding round and
    came out of scoring with a final 1, because round_results was never
    passed to the scorer at all.
    """

    def test_exercise_score_reaches_the_scorer(self):
        prompt = pb.build_scoring_prompt("CTX", [], round_results=[_exercise()])
        assert "EXERCISES THEY ACTUALLY SAT" in prompt
        assert "8/10" in prompt

    def test_names_the_question_not_just_its_id(self):
        prompt = pb.build_scoring_prompt("CTX", [], round_results=[_exercise()])
        # Resolved through the catalogue, so the scorer reads a title.
        assert "lru-cache-design" not in prompt
        assert "Coding exercise" in prompt

    def test_hidden_test_results_reach_the_scorer(self):
        prompt = pb.build_scoring_prompt("CTX", [], round_results=[_exercise()])
        assert "1 of 2 HIDDEN tests passed" in prompt

    def test_grader_findings_and_notes_reach_the_scorer(self):
        prompt = pb.build_scoring_prompt("CTX", [], round_results=[_exercise()])
        assert "Correct doubly-linked list." in prompt
        assert "stale node" in prompt
        assert "repeated put" in prompt

    def test_a_high_exercise_score_cannot_be_silently_ignored(self):
        prompt = pb.build_scoring_prompt("CTX", [], round_results=[_exercise(review={"score": 10})])
        assert "MUST move the final score" in prompt
        assert "name that reason plainly in weaknesses" in prompt

    def test_a_failed_exercise_is_not_rescued_by_good_talk(self):
        prompt = pb.build_scoring_prompt("CTX", [], round_results=[_exercise()])
        assert "does not rescue a failed exercise" in prompt

    def test_one_exercise_is_weighted_lighter_than_two(self):
        one = pb.build_scoring_prompt("CTX", [], round_results=[_exercise()])
        two = pb.build_scoring_prompt(
            "CTX", [], round_results=[_exercise(), _exercise(index=2, question_id="merge-intervals")]
        )
        assert "roughly a THIRD" in one
        assert "roughly HALF" in two

    def test_the_task_line_stops_calling_it_a_pure_resume_defence(self):
        with_exercise = pb.build_scoring_prompt("CTX", [], round_results=[_exercise()])
        assert "graded exercises" in with_exercise

    # --- the conversation-only path must be untouched ---

    def test_conversation_only_gets_no_block_at_all(self):
        # An HR or IB candidate the planner correctly gave no exercise must
        # not be told they sat none: that reads as a gap and would cap a
        # whole vertical for a decision the product made for them.
        prompt = pb.build_scoring_prompt("CTX", [], round_results=[])
        assert "EXERCISES THEY ACTUALLY SAT" not in prompt
        assert "graded exercises" not in prompt

    def test_conversation_rounds_are_not_mistaken_for_exercises(self):
        prompt = pb.build_scoring_prompt(
            "CTX", [], round_results=[{"index": 0, "kind": "CONVERSATION"}]
        )
        assert "EXERCISES THEY ACTUALLY SAT" not in prompt

    def test_passing_nothing_is_byte_identical_to_before(self):
        # Every interview created before this change has round_results NULL.
        utterances = [{"speaker": "candidate", "text": "I did X."}]
        assert pb.build_scoring_prompt("CTX", utterances) == pb.build_scoring_prompt(
            "CTX", utterances, round_results=None
        )

    def test_a_stale_question_id_does_not_crash_scoring(self):
        # Questions can be removed from the catalogue; an interview mid-flight
        # must still be scorable.
        prompt = pb.build_scoring_prompt(
            "CTX", [], round_results=[_exercise(question_id="deleted-question")]
        )
        assert "deleted-question" in prompt
        assert "8/10" in prompt

    def test_survives_a_round_result_with_missing_fields(self):
        prompt = pb.build_scoring_prompt(
            "CTX", [], round_results=[{"index": 1, "question_id": "merge-intervals"}]
        )
        assert "EXERCISES THEY ACTUALLY SAT" in prompt


class TestBuildResumeDisplayText:
    def test_includes_resume_sections(self):
        text = pb.build_resume_display_text(_anonymized())
        assert "WORK EXPERIENCE" in text

    def test_never_leaks_the_roast(self):
        # The pane must not become an answer key for the questions coming.
        text = pb.build_resume_display_text(_anonymized())
        roast = _roast()
        assert roast["verdict"] not in text
        assert roast["roast"] not in text

    def test_malformed_artifact_returns_empty_rather_than_raising(self):
        # A missing artifact must not take the whole interview down.
        assert pb.build_resume_display_text({}) == ""
        assert pb.build_resume_display_text({"content": "not a dict"}) == ""


class TestSkipAndEndInstructions:
    def test_gives_the_model_an_escape_from_stonewalling(self):
        # v1 bug: it pressed forever and never moved on, because the
        # instruction to press had no escape hatch.
        instruction = pb.build_live_system_instruction("CTX")
        assert "ONCE" in instruction
        assert "skip_question" in instruction

    def test_tells_it_to_actually_call_the_tool_not_just_threaten(self):
        instruction = pb.build_live_system_instruction("CTX")
        assert "end_interview" in instruction
        assert "without actually calling the tool" in instruction


class TestBreadth:
    """
    The observed failure was the interviewer grinding one resume bullet for
    the whole ten minutes. Breadth has to be instructed; it does not happen
    on its own.
    """

    def test_states_the_actual_time_budget(self):
        # A constant would drift from whatever the planner allocated.
        assert "ABOUT 7 MINUTES" in pb.build_live_system_instruction("CTX", 7)
        assert "ABOUT 12 MINUTES" in pb.build_live_system_instruction("CTX", 12)

    def test_asks_for_several_areas_not_one(self):
        instruction = pb.build_live_system_instruction("CTX")
        assert "FOUR OR FIVE distinct areas" in instruction

    def test_caps_follow_ups_and_says_to_move_on_regardless(self):
        instruction = pb.build_live_system_instruction("CTX")
        assert "at most TWICE" in instruction
        assert "MOVE ON anyway" in instruction


class TestDebriefDiscussesTheSolution:
    def _addendum(self, review=None, conduct=""):
        question = {"format": "CODE", "prompt": "Design an LRU cache.", "difficulty": "medium"}
        return pb.build_debrief_addendum([], question, "class LRUCache: pass", review, conduct)

    def test_asks_for_a_real_discussion_not_a_single_jab(self):
        text = self._addendum()
        assert "three or four" in text
        assert "complexity they claimed" in text
        assert "what breaks first when the input gets very large" in text

    def test_edge_cases_are_asked_as_scenarios_not_hints(self):
        assert "not \"you forgot" in self._addendum()

    def test_never_reveals_that_a_hidden_test_failed(self):
        text = self._addendum()
        assert "WITHOUT naming the case" in text

    def test_carries_conduct_through(self):
        text = self._addendum(conduct="- They PASTED code in.")
        assert "They PASTED code in." in text
        # Asserted on one line rather than the whole sentence -- the
        # template wraps, and a wrap is not a behaviour change.
        assert "never to be read out as an" in text


# ---------------------------------------------------------------------------
# Link-list labelling and heading de-duplication (twin of the roast worker)
# ---------------------------------------------------------------------------

def _lines(n):
    return "\n".join(f"Built thing number {i} for the platform." for i in range(n))


def _two_page_blocks():
    """A real 2-page shape: contact header, sections with headings, page 1's
    hidden link list inside the last block of page 1, then page 2's section."""
    return {
        "other": [{"text": "Jane Doe\n{{EMAIL_1}}\n{{URL_1}}\n{{URL_2}}",
                   "source_span": {"start": 0, "end": 60}}],
        "summary": [{"text": "Professional Summary\nBackend engineer.",
                     "source_span": {"start": 70, "end": 120},
                     "heading": "Professional Summary"}],
        "experience": [{"text": "Experience\n" + _lines(12),
                        "source_span": {"start": 130, "end": 900},
                        "heading": "Experience"}],
        "projects": [{"text": "Projects\nBuilt a thing.\n{{URL_3}}\n{{URL_4}}\n{{URL_5}}\n{{URL_6}}",
                      "source_span": {"start": 1000, "end": 1200},
                      "heading": "Projects"}],
        "certifications": [{"text": "Certifications\nAWS SA",
                            "source_span": {"start": 1300, "end": 1400},
                            "heading": "Certifications"}],
    }


class TestInterviewLinkAndHeadingHandling:
    """
    This copy also feeds build_resume_display_text, which renders into the
    candidate's OWN side pane during the live call -- so a mistake here is
    shown to the person being interviewed, not just to the model.
    """

    def test_a_mid_document_link_list_is_labelled(self):
        out = pb._format_resume_sections(_two_page_blocks())
        assert out.count(pb._LINK_DUMP_NOTE) == 1
        assert out.index(pb._LINK_DUMP_NOTE) < out.index("[URL_3]")
        assert out.index("[URL_6]") < out.index("[CERTIFICATIONS]")

    def test_the_contact_header_is_never_mistaken_for_a_link_list(self):
        # "[EMAIL_1] / [URL_1] / [URL_2]" one per line at the very top.
        out = pb._format_resume_sections(_two_page_blocks())
        top = out.split("[SUMMARY / OBJECTIVE]")[0]
        assert pb._LINK_DUMP_NOTE not in top

    def test_headings_are_not_repeated_under_their_labels(self):
        out = pb._format_resume_sections(_two_page_blocks())
        assert "Professional Summary" not in out
        assert "Experience\n" not in out.replace("[WORK EXPERIENCE]\n", "")
        assert "Certifications\n" not in out.replace("[CERTIFICATIONS]\n", "")

    def test_no_content_is_lost(self):
        out = pb._format_resume_sections(_two_page_blocks())
        for kept in ("Jane Doe", "Backend engineer.", "Built thing number 11",
                     "Built a thing.", "AWS SA", "[URL_3]", "[URL_6]"):
            assert kept in out

    def test_legacy_blocks_without_the_heading_field_render_as_before(self):
        blocks = {"summary": [{"text": "Summary\nBackend engineer.",
                               "source_span": {"start": 0, "end": 30}}]}
        assert pb._format_resume_sections(blocks) == "[SUMMARY / OBJECTIVE]\nSummary\nBackend engineer."


class TestTwinParityWithTheRoastWorker:
    """
    backend/ and workers/ deliberately duplicate the renderer (they are
    separately deployable, with no shared import root). That is only safe if
    the two copies never drift, and until now nothing checked. This does: same
    input, byte-identical output.
    """

    def test_both_copies_render_the_same_thing(self):
        from workers.scoring.pipeline import prompt_builder as wpb

        cases = [
            _two_page_blocks(),
            {"summary": [{"text": "Summary\nBackend engineer.",
                          "source_span": {"start": 0, "end": 30}}]},
            {"summary": [{"text": "Summary\nBackend engineer.",
                          "source_span": {"start": 0, "end": 30},
                          "heading": "Summary"}]},
            {"projects": [{"text": "Projects", "source_span": {"start": 0, "end": 8},
                           "heading": "Projects"}]},
            {"other": [{"text": "{{EMAIL_1}}\n{{PHONE_1}}\n{{URL_1}}",
                        "source_span": {"start": 0, "end": 30}}]},
            {},
        ]
        for blocks in cases:
            assert pb._format_resume_sections(blocks) == wpb._format_resume_sections(blocks)

    def test_the_link_note_and_thresholds_are_identical(self):
        from workers.scoring.pipeline import prompt_builder as wpb
        assert pb._LINK_DUMP_NOTE == wpb._LINK_DUMP_NOTE
        assert pb._HEADER_ZONE_LINES == wpb._HEADER_ZONE_LINES
        assert pb._MIN_LINK_DUMP_LINES == wpb._MIN_LINK_DUMP_LINES


class TestCandidateSidePane:
    def test_the_candidates_own_pane_has_no_doubled_heading_and_keeps_everything(self):
        # build_resume_display_text renders straight into the candidate's side
        # pane during the live call, so this is what the person being
        # interviewed actually reads.
        shown = pb.build_resume_display_text({"content": {"blocks": _two_page_blocks()}})
        assert "Professional Summary" not in shown
        assert "Backend engineer." in shown
        assert "AWS SA" in shown

    def test_a_malformed_artifact_still_degrades_to_empty(self):
        assert pb.build_resume_display_text({}) == ""
        assert pb.build_resume_display_text({"content": {"blocks": "nope"}}) == ""
