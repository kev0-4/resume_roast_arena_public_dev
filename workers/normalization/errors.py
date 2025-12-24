class NormalizationError(Exception):
    pass

class TransientNormalizationError(NormalizationError):
    """Retryable: infra failures"""

class PermanentNormalizationError(NormalizationError):
    """Bad input: malformed extracted.json"""
