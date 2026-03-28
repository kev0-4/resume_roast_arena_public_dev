class ScoringError(Exception):
    """Base class for all scoring-related failures."""


class TransientScoringError(ScoringError):
    """
    Errors that MAY succeed on retry.
    Example: network timeout, blob temporary failure.
    """
    pass


class PermanentScoringError(ScoringError):
    """
    Errors that will NEVER succeed on retry.
    Example: corrupt file, unsupported format.
    """
    pass
