# workers/extraction/errors.py

class ExtractionError(Exception):
    """Base class for all extraction-related failures."""


class TransientExtractionError(ExtractionError):
    """
    Errors that MAY succeed on retry.
    Example: network timeout, blob temporary failure.
    """
    pass


class PermanentExtractionError(ExtractionError):
    """
    Errors that will NEVER succeed on retry.
    Example: corrupt file, unsupported format.
    """
    pass
