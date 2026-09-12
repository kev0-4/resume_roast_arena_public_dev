"""
backend/src/interview/llm_client.py

Two Gemini interactions for the mock-interview feature, and they are very
different in kind:

1. create_ephemeral_token -- mints a short-lived, single-use credential the
   BROWSER uses to open its own Live API WebSocket. The conversation never
   passes through this server. That is the whole point: a relay hop would
   add latency to every syllable, and latency is the entire reason this
   feature was rebuilt.

2. generate_score -- one ordinary structured-output call at the end, over
   the transcript. Mirrors workers/llm/pipeline/client.py's
   singleton-client + response_schema pattern exactly.

Security invariant, same as workers/llm/pipeline/client.py: callers must
only ever build prompts from the anonymized resume artifact, never raw or
normalized content. This module doesn't enforce that (it sends whatever
prompt it's given) -- it's enforced by interview/prompt_builder.py only
ever being handed anonymized.json.
"""

import datetime
from typing import Tuple

from google import genai

from ..config import (
    GEMINI_API_KEY,
    GEMINI_INTERVIEW_MODEL,
    GEMINI_LIVE_MODEL,
    INTERVIEW_TOKEN_EXPIRE_SECONDS,
    INTERVIEW_TOKEN_NEW_SESSION_SECONDS,
)
from .schemas import InterviewScoreResponse

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


async def create_ephemeral_token(system_instruction: str) -> Tuple[str, datetime.datetime]:
    """
    Mints a single-use Live API credential for one interview.

    Returns (token_name, expire_time). The token name is what the browser
    passes as its API key; our real GEMINI_API_KEY never leaves this
    process.

    The constraints MUST carry the whole config, not just the model. This
    is not a preference -- it was found by probing:

      - constraints naming only the model: the session is rejected at
        connect with "The requested combination of response modalities
        (TEXT) is not supported by the model", because a constrained token
        with no config makes the server apply its own TEXT default and
        ignore what the client asked for. Reproduced every time.
      - constraints carrying model + config: connects and speaks.
      - no constraints at all: also connects, but locks nothing down.

    So pinning the full config is simultaneously the fix and the control.

    What protects this token, likewise verified against the live API:

    - uses=1 IS enforced. A second connection attempt with the same token
      is rejected with "Token has been used too many times".
    - Both expiry times are enforced.
    - The MODEL field of the constraints is not, on its own, a hard lock:
      a token naming one model was previously able to open a session on a
      different, pricier one. Blast radius stays one session per token,
      which is what the short lifetimes are for.

    Raises:
        google.genai.errors.APIError -- caller turns this into a 503.
    """
    client = _get_client()
    now = datetime.datetime.now(datetime.timezone.utc)
    expire_time = now + datetime.timedelta(seconds=INTERVIEW_TOKEN_EXPIRE_SECONDS)

    token = await client.aio.auth_tokens.create(
        config=genai.types.CreateAuthTokenConfig(
            uses=1,
            expire_time=expire_time,
            new_session_expire_time=now + datetime.timedelta(seconds=INTERVIEW_TOKEN_NEW_SESSION_SECONDS),
            live_connect_constraints=genai.types.LiveConnectConstraints(
                model=GEMINI_LIVE_MODEL,
                config=genai.types.LiveConnectConfig(
                    response_modalities=["AUDIO"],
                    system_instruction=system_instruction,
                    input_audio_transcription=genai.types.AudioTranscriptionConfig(),
                    output_audio_transcription=genai.types.AudioTranscriptionConfig(),
                ),
            ),
        )
    )
    if not token.name:
        raise ValueError("Gemini returned an auth token with no name")
    return token.name, expire_time


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
