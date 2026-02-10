class AnonymizationError(Exception):
    """Base class for all Anonymization-related failures."""


class TransientEAnonymizationError(AnonymizationError):
    """
    Errors that MAY succeed on retry.
    Example: network timeout, blob temporary failure.
    """
    pass


class PermanentAnonymizationError(AnonymizationError):
    """
    Errors that will NEVER succeed on retry.
    Example: corrupt file, unsupported format.
    """
    pass
