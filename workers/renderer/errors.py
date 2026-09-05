class RenderError(Exception):
    """Base class for all renderer worker failures."""


class TransientRenderError(RenderError):
    """
    Retryable -- network failures, browser crashes, blob/DB transient errors.
    """


class PermanentRenderError(RenderError):
    """
    Non-retryable -- malformed upstream artifact.
    """
