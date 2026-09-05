"""
workers/llm/pipeline/client.py

LLM inference client — calls the Gemini API to generate a resume roast.

Security invariant: this module only ever receives the prompt string built
from the anonymized artifact.  Raw or normalized resume content NEVER reaches
this module or the Gemini API.

Model: gemini-3.8-flash by default (configurable via GEMINI_ROAST_MODEL).
Provider may change (e.g. to OpenAI) later — this module is the only place
that needs to change.
"""

import os
from google import genai
from typing import Tuple

_MODEL = os.getenv("GEMINI_ROAST_MODEL", "gemini-3.8-flash")
_MAX_OUTPUT_TOKENS = 1024

_async_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _async_client
    if _async_client is None:
        _async_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _async_client


async def call_roast_llm(prompt: str) -> Tuple[str, dict, str]:
    """
    Call the Gemini API and return (response_text, usage_dict, model_used).

    Raises:
        google.genai.errors.ServerError → caller should wrap as TransientLLMError
        google.genai.errors.ClientError → caller inspects .code (429 vs other 4xx)
    """
    client = _get_client()

    response = await client.aio.models.generate_content(
        model=_MODEL,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            max_output_tokens=_MAX_OUTPUT_TOKENS,
        ),
    )

    text = response.text or ""
    usage = {
        "input_tokens": response.usage_metadata.prompt_token_count,
        "output_tokens": response.usage_metadata.candidates_token_count,
    }
    model_used: str = response.model_version or _MODEL

    return text, usage, model_used
