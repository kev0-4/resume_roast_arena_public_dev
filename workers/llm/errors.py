class LLMError(Exception):
    """Base class for all LLM roast worker failures."""


class TransientLLMError(LLMError):
    """
    Retryable — network failures, rate limits, API 5xx.
    """


class PermanentLLMError(LLMError):
    """
    Non-retryable — malformed prompt, unparseable LLM output after retries.
    """
