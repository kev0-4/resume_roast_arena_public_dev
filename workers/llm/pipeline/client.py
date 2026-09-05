"""
workers/llm/pipeline/client.py

LLM inference client — calls the Anthropic API to generate a resume roast.

Security invariant: this module only ever receives the prompt string built
from the anonymized artifact.  Raw or normalized resume content NEVER reaches
this module or the Anthropic API.

Model: claude-haiku-4-5 by default (configurable via ANTHROPIC_ROAST_MODEL).
Upgrade to claude-opus-5 for higher-quality roasts at greater cost.
"""

import os
import anthropic
from typing import Tuple

_MODEL = os.getenv("ANTHROPIC_ROAST_MODEL", "claude-haiku-4-5")
_MAX_TOKENS = 1024

_async_client: anthropic.AsyncAnthropic | None = None


def _get_async_client() -> anthropic.AsyncAnthropic:
    global _async_client
    if _async_client is None:
        _async_client = anthropic.AsyncAnthropic()
    return _async_client


async def call_roast_llm(prompt: str) -> Tuple[str, dict, str]:
    """
    Call the Anthropic API and return (response_text, usage_dict, model_used).

    Raises:
        anthropic.RateLimitError  → caller should wrap as TransientLLMError
        anthropic.APIStatusError  → caller inspects status_code
        anthropic.APIConnectionError → caller wraps as TransientLLMError
    """
    client = _get_async_client()

    async with client.messages.stream(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = await stream.get_final_message()

    text = next(
        (block.text for block in message.content if block.type == "text"),
        "",
    )
    usage = {
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }
    model_used: str = message.model

    return text, usage, model_used
