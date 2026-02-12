'''
Docstring for workers.anonymization.pipeline.loader
Loader for Anonymization pipeline
normalized/<session_id>/normalized.json
Validate minimum required shape
Return a trusted dict to downstream pipeline stages
'''


import json
from typing import Dict, Any

from backend.src.services.blob import read_blob
from ..errors import (
    TransientAnonymizationError,
    PermanentAnonymizationError
)

REQUIRED_TOP_LEVEL_FIELDS = {
    "session_id",
    "content",
    "signals",
    "metrics",
    "timestamps",
}

REQUIRED_CONTENT_FIELDS = {
    "blocks",
    "entities"
}

REQUIRED_TIMESTAMP_FIELDS = {
    "normalized_at",
}


def load_normalized(blob_path: str) -> Dict[str, Any]:
    ''' Loads and validated normalized json , returns trusted normalized payload'''
    # read blob
    try:
        raw_bytes = read_blob(blob_path=blob_path)
    except Exception as e:
        raise TransientAnonymizationError(
            f"Anonymization: Failed to read normalized blob {e}")

    # parse raw_bytes
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except Exception as e:
        raise PermanentAnonymizationError(
            f"Anonymization: Converion of raw_bytes failed,Invalid JSON in normalized artifact: {e} "
        )
    if not isinstance(payload, dict):
        raise PermanentAnonymizationError(
            "Anonymization : normalized artifact is not JSON"
        )

    # validate top level fields
    missing = REQUIRED_TOP_LEVEL_FIELDS - payload.keys()
    if missing:
        raise PermanentAnonymizationError(
            f"Anonymization: Normalized artifacts missing fields {missing}"
        )

    # Validate content structure
    content = payload.get("content")
    if not isinstance(content, dict):
        raise PermanentAnonymizationError(
            f"Anonymization: Cannot validate content structure, content must be an object {content}"
        )
    missing_content = REQUIRED_CONTENT_FIELDS - content.keys()
    if missing_content:
        raise PermanentAnonymizationError(
            f"Anonymization: Content missing fields {missing_content}"
        )

    if not isinstance(content.get("blocks"), dict):
        raise PermanentAnonymizationError(
            f"Anonymization: content.blocks must be an object {content.get("blocks")}"
        )

    if not isinstance(content.get("entities"), dict):
        raise PermanentAnonymizationError(
            f"Anonymization: content.blocks must be an object {content.get("entities")}"
        )

    # validate timestamps
    timestamps = payload.get("timestamps")
    if not isinstance(timestamps, dict):
        raise PermanentAnonymizationError(
            f"Anonymization: timestamps must be an object {timestamps}"
        )

    missing_ts = REQUIRED_TIMESTAMP_FIELDS - timestamps.keys()
    if missing_ts:
        raise PermanentAnonymizationError(
            f"Anonymization: timestamp missing fields  {missing_ts}"
        )

    return payload
