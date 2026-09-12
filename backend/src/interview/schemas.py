"""
backend/src/interview/schemas.py

Contract layer for the mock-interview feature's two Gemini calls -- same
philosophy as workers/llm/schemas.py's LLMStructuredResponse: these classes
*are* the response_schema passed directly to GenerateContentConfig, not
just an internal convenience type.
"""

from typing import List
from pydantic import BaseModel


SCORE_MIN = 1
SCORE_MAX = 10


class InterviewTurnResponse(BaseModel):
    """
    Asked of Gemini on every turn (opening question and every subsequent
    answer alike -- on the opening call answer_transcript/reaction_text
    are unused/empty, there's no prior answer to transcribe or react to).

    answer_transcript exists because Gemini is given the raw audio and
    asked to transcribe it in the SAME call that produces the reaction and
    next question (see interview/llm_client.py) -- there's no separate STT
    step. This is also what makes subsequent turns' prompts possible:
    interview/prompt_builder.py's conversation-so-far block is built from
    these transcripts as plain text, not by re-sending prior audio.

    is_final_turn is a signal, not an enforcement mechanism: the server
    always force-overrides it to True once turn_count would hit max_turns,
    regardless of what the model returns here (validator.py). This field
    only lets the model end an interview *early* when it genuinely judges
    enough ground has been covered.
    """
    answer_transcript: str
    reaction_text: str
    next_question: str
    is_final_turn: bool


class InterviewScoreResponse(BaseModel):
    """
    Asked of Gemini once, at the end, over the full transcript -- a
    separate call/prompt from the per-turn one so scoring always reasons
    over the complete conversation rather than just the final exchange.
    """
    score: int
    strengths: List[str]
    weaknesses: List[str]
    next_steps: List[str]
