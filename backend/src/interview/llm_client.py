"""
backend/src/interview/llm_client.py

Gemini calls for the mock-interview feature's structured text responses
(opening question, per-turn reaction+next-question, final score) --
mirrors workers/llm/pipeline/client.py's singleton-client + response_schema
pattern exactly. TTS is deliberately a separate module (tts_client.py):
confirmed via a real call this session that the interview model
(GEMINI_INTERVIEW_MODEL) does NOT support response_modalities=["AUDIO"]
(it just silently returns text), and the TTS-capable model does NOT
support response_schema/JSON mode ("JSON mode is not enabled for this
model") -- these are two genuinely separate calls to two different models,
not a config choice.

Audio input + response_schema DO work together in one call, confirmed
against the real API: the model transcribes the attached audio and
produces the structured JSON response in the same request, no separate
STT step needed.

Security invariant, same as workers/llm/pipeline/client.py: callers must
only ever build these prompts from the anonymized resume artifact, never
raw/normalized content. This module itself doesn't enforce that (it just
sends whatever prompt/audio it's given) -- enforced by
interview/prompt_builder.py only ever being handed anonymized.json.
"""

from typing import Tuple

from google import genai

from ..config import GEMINI_API_KEY, GEMINI_INTERVIEW_MODEL
from .schemas import InterviewTurnResponse, InterviewScoreResponse

_MAX_OUTPUT_TOKENS = 1024

_async_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _async_client
    if _async_client is None:
        _async_client = genai.Client(api_key=GEMINI_API_KEY)
    return _async_client


def _usage_from(response) -> dict:
    return {
        "input_tokens": response.usage_metadata.prompt_token_count,
        "output_tokens": response.usage_metadata.candidates_token_count,
    }


async def generate_opening_question(prompt: str) -> Tuple[InterviewTurnResponse, dict, str]:
    """
    Text-only call (no audio input yet -- this is the very first question,
    there's nothing to react to). Returns (parsed_response, usage, model_used).

    Raises:
        google.genai.errors.ServerError / ClientError -- caller wraps as
            transient/permanent per the same convention as the roast worker.
        ValueError -- response_schema failed to parse.
    """
    client = _get_client()
    response = await client.aio.models.generate_content(
        model=GEMINI_INTERVIEW_MODEL,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
            response_schema=InterviewTurnResponse,
        ),
    )
    if response.parsed is None:
        raise ValueError(f"Gemini response did not match response_schema: {response.text!r}")
    return response.parsed, _usage_from(response), (response.model_version or GEMINI_INTERVIEW_MODEL)


async def generate_turn_response(
    prompt: str, audio_bytes: bytes, audio_mime_type: str
) -> Tuple[InterviewTurnResponse, dict, str]:
    """
    The one multimodal call per turn: audio input (the candidate's spoken
    answer) + response_schema, in the same request -- confirmed working
    against the real API this session. Gemini transcribes the audio AND
    produces the structured reaction/next-question in one shot.
    """
    client = _get_client()
    response = await client.aio.models.generate_content(
        model=GEMINI_INTERVIEW_MODEL,
        contents=[
            prompt,
            genai.types.Part.from_bytes(data=audio_bytes, mime_type=audio_mime_type),
        ],
        config=genai.types.GenerateContentConfig(
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
            response_schema=InterviewTurnResponse,
        ),
    )
    if response.parsed is None:
        raise ValueError(f"Gemini response did not match response_schema: {response.text!r}")
    return response.parsed, _usage_from(response), (response.model_version or GEMINI_INTERVIEW_MODEL)


async def generate_score(prompt: str) -> Tuple[InterviewScoreResponse, dict, str]:
    """The one end-of-interview scoring call, over the full transcript as text."""
    client = _get_client()
    response = await client.aio.models.generate_content(
        model=GEMINI_INTERVIEW_MODEL,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
            response_schema=InterviewScoreResponse,
        ),
    )
    if response.parsed is None:
        raise ValueError(f"Gemini response did not match response_schema: {response.text!r}")
    return response.parsed, _usage_from(response), (response.model_version or GEMINI_INTERVIEW_MODEL)
