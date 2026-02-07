'''
Docstring for workers.normalization.pipeline.assembler
Final artificat of normalization layer
This gurantess schema stability 
'''
'''
Output normalized.json
{
  "session_id": "...",
  "normalization_version": "1.0",

  "source": {
    "extraction_version": "...",
    "used_ocr": true,
    "confidence": 0.87
  },

  "content": {
    "blocks": {...},
    "entities": {...}
  },

  "signals": {...},
  "metrics": {...},

  "timestamps": {
    "extracted_at": "...",
    "normalized_at": "..."
  }
}

'''
from typing import Dict, Any
from datetime import datetime
from uuid import UUID

NORMALIZATION_VERSION = "1.0"


def assemble_normalized(
    *,
    session_id: str | UUID,
    extracted: Dict[str, Any],
    blocks: Dict[str, list],
    entities: Dict[str, list],
    signals: Dict[str, bool],
    metrics: Dict[str, Any],
    normalized_at: datetime,
) -> Dict[str, Any]:
    """
    Assemble normalized resume artifact.

    Args:
        session_id: Resume session ID
        extracted: Extracted payload (from extracted.json)
        blocks: Sectioned text blocks
        entities: Extracted entities with spans
        signals: Boolean/categorical signals
        metrics: Numeric metrics
        normalized_at: Timestamp when normalization completed

    Returns:
        Normalized artifact ready for persistence
    """

    # ------------------------------------------------------------
    # 1. Shallow sanity checks (do NOT over-validate)
    # ------------------------------------------------------------
    # TODO:
    # - Assert required keys exist in extracted
    # - Fail fast if extracted is malformed (should be rare)
    if not isinstance(extracted, dict):
        raise ValueError("extracted payload must be a dict")
    if "extraction_version" not in extracted:
        raise ValueError("missing extraction_version in extracted payload")
    
    timestamps = extracted.get("timestamps")
    if not isinstance(timestamps, dict):
        raise ValueError("missing timestamps in extracted payload")

    if "completed_at" not in timestamps:
        raise ValueError("missing timestamps.completed_at in extracted payload")
    source = extracted.get("source")
    if not isinstance(source, dict):
        raise ValueError("missing source metadata in extracted payload")



    # ------------------------------------------------------------
    # 2. Build source metadata
    # ------------------------------------------------------------
    source = {
        "extraction_version": extracted.get("extraction_version"),
        "used_ocr": extracted.get("source", {}).get("used_ocr"),
        "confidence": extracted.get("source", {}).get("confidence"),
    }

    # ------------------------------------------------------------
    # 3. Assemble final payload
    # ------------------------------------------------------------
    normalized: Dict[str, Any] = {
        "session_id": str(session_id),
        "normalization_version": NORMALIZATION_VERSION,

        "source": source,

        "content": {
            "blocks": blocks,
            "entities": entities,
        },

        "signals": signals,
        "metrics": metrics,

        "timestamps": {
            "extracted_at": extracted.get("timestamps", {}).get("completed_at"),
            "normalized_at": normalized_at.isoformat(),
        },
    }

    # ------------------------------------------------------------
    # 4. Return assembled artifact
    # ------------------------------------------------------------
    return normalized