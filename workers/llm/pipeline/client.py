"""
workers/llm/pipeline/client.py

LLM inference client — calls the Gemini API to generate a resume roast.

Security invariant: this module only ever receives the prompt string built
from the anonymized artifact.  Raw or normalized resume content NEVER reaches
this module or the Gemini API.

Model: gemini-3.5-flash-lite by default (configurable via GEMINI_ROAST_MODEL) —
chosen for its higher free-tier rate limits.
Provider may change (e.g. to OpenAI) later — this module is the only place
that needs to change.

Structured output (response_schema=LLMStructuredResponse, JSON mode): was a
hand-rolled "VERDICT:/ROAST:/FIXES:/HIGHLIGHTS:" text format regex-parsed by
validator.py, which meant any formatting slip from the model was an outright
parse failure (a real, silently-costly failure mode -- see
processor.py's PermanentLLMError on parse errors, which burns the call's
tokens for nothing). JSON mode constrains the model to the schema directly
instead of hoping it follows text formatting instructions; adding the new
quality_flags field to a schema is a one-line change, versus another
hand-parsed text section.
"""

import os
from google import genai
from typing import Tuple

from ..schemas import LLMStructuredResponse

_MODEL = os.getenv("GEMINI_ROAST_MODEL", "gemini-3.5-flash-lite")
# Bumped from 1024 -- the HIGHLIGHTS section (2-4 quoted excerpts + comments)
# added real headroom pressure on top of verdict/roast/fixes; 1024 was
# already close to the response's natural length before this addition.
# quality_flags adds a handful more tokens on top (a short list of enum
# values) -- not bumped further, well within the existing headroom.
_MAX_OUTPUT_TOKENS = 1536

_async_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _async_client
    if _async_client is None:
        _async_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _async_client


async def call_roast_llm(prompt: str) -> Tuple[LLMStructuredResponse, dict, str]:
    """
    Call the Gemini API and return (parsed_response, usage_dict, model_used).

    Raises:
        google.genai.errors.ServerError → caller should wrap as TransientLLMError
        google.genai.errors.ClientError → caller inspects .code (429 vs other 4xx)
        ValueError → response_schema validation failed to parse (caller wraps
                     as PermanentLLMError, same as a text-format parse failure
                     used to be)
    """
    client = _get_client()

    response = await client.aio.models.generate_content(
        model=_MODEL,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
            response_schema=LLMStructuredResponse,
        ),
    )

    if response.parsed is None:
        raise ValueError(f"Gemini response did not match response_schema: {response.text!r}")

    usage = {
        "input_tokens": response.usage_metadata.prompt_token_count,
        "output_tokens": response.usage_metadata.candidates_token_count,
    }
    model_used: str = response.model_version or _MODEL

    return response.parsed, usage, model_used
