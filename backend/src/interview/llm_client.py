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


async def create_ephemeral_token() -> Tuple[str, datetime.datetime]:
    """
    Mints a single-use Live API credential for one interview.

    Returns (token_name, expire_time). The token name is what the browser
    passes as its API key; our real GEMINI_API_KEY never leaves this
    process.

    What actually protects this token, verified against the live API rather
    than taken from docs:

    - uses=1 IS enforced. A second connection attempt with the same token
      is rejected with "Token has been used too many times".
    - The two expiry times are enforced.
    - live_connect_constraints is NOT enforced. A token minted naming this
      model was able to open a session on a different, more expensive one.
      It is therefore set as a statement of intent, not a control, and the
      short lifetimes above are what actually bound the damage.

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
            live_connect_constraints=genai.types.LiveConnectConstraints(model=GEMINI_LIVE_MODEL),
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
