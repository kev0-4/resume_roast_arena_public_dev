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
        assert pb.normalize_placeholders("Contact: {{EMAIL_1}}") == "Contact: [EMAIL]"

    def test_multiple_placeholders(self):
        assert pb.normalize_placeholders("{{EMAIL_1}} {{PHONE_2}}") == "[EMAIL] [PHONE]"

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
