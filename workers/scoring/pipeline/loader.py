"""
Loader for scoring pipeline.

Responsibilities:
- Load anonymized.json
- Validate minimal required structure
- Return trusted payload
"""

import json
from typing import Dict, Any

from backend.src.services.blob import read_blob

from ..errors import (
    TransientScoringError,
    PermanentScoringError,
)

# ------------------------------------------------------------
# Required fields for scoring stage
# ------------------------------------------------------------
REQUIRED_TOP_LEVEL_FIELDS = {
    "session_id",
    "content",
    "signals",
    "metrics",
    "timestamps",
}


def load_anonymized(blob_path: str) -> Dict[str, Any]:
    """
    Load and validate anonymized.json.

    Raises:
        TransientScoringError → blob read failure
        PermanentScoringError → invalid structure
    """

    # ------------------------------------------------------------
    # 1. Read blob
    # ------------------------------------------------------------
    try:
        raw_bytes = read_blob(blob_path)
    except Exception as e:
        raise TransientScoringError(
            f"Failed to read anonymized blob: {e}"
        )

    # ------------------------------------------------------------
    # 2. Parse JSON
    # ------------------------------------------------------------
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except Exception as e:
        raise PermanentScoringError(
            f"Invalid JSON in anonymized artifact: {e}"
        )

    # ------------------------------------------------------------
    # 3. Basic structure validation
    # ------------------------------------------------------------
    if not isinstance(payload, dict):
        raise PermanentScoringError(
            "Anonymized artifact is not a JSON object"
        )

    missing_fields = REQUIRED_TOP_LEVEL_FIELDS - payload.keys()
    if missing_fields:
        raise PermanentScoringError(
            f"Anonymized artifact missing fields: {missing_fields}"
        )

    # ------------------------------------------------------------
    # 4. Validate content shape (minimal)
    # ------------------------------------------------------------
    content = payload.get("content")
    if not isinstance(content, dict):
        raise PermanentScoringError("content must be a dict")

    blocks = content.get("blocks")
    if not isinstance(blocks, dict):
        raise PermanentScoringError("content.blocks must be a dict")

    # ------------------------------------------------------------
    # 5. Validate signals & metrics
    # ------------------------------------------------------------
    if not isinstance(payload.get("signals"), dict):
        raise PermanentScoringError("signals must be a dict")

    if not isinstance(payload.get("metrics"), dict):
        raise PermanentScoringError("metrics must be a dict")

    # ------------------------------------------------------------
    # 6. Return trusted payload
    # ------------------------------------------------------------
    return payload