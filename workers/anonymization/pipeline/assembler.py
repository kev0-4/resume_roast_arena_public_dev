'''

Docstring for workers.anonymization.pipeline.assembler

Assembels final anonymized artifact
'''


from typing import Dict, Any
from datetime import datetime
from uuid import UUID

from ..errors import PermanentAnonymizationError

ANONYMIZATION_VERSION = "1.0"



def assemble_anonymized(
    *,
    session_id: str | UUID,
    normalized: Dict[str, Any],
    redacted_blocks: Dict[str, Any],
    redactions: Dict[str, Any],
    anonymized_at: datetime,
) -> Dict[str, Any]:
    
    if not isinstance(normalized, dict):
        raise PermanentAnonymizationError("Assembler: normalized payload must be a dict")

    if "signals" not in normalized or "metrics" not in normalized:
        raise PermanentAnonymizationError("Assembler: normalized artifact missing signals or metrics")

    timestamps = normalized.get("timestamps")
    if not isinstance(timestamps, dict):
        raise PermanentAnonymizationError("Assembler: normalized artifact missing timestamps")

    if "normalized_at" not in timestamps:
        raise PermanentAnonymizationError("Assembler: missing normalized_at in timestamps")

    #Building the artifact
    anonymized: Dict[str, Any] = {
        "session_id": str(session_id),
        "anonymization_version": ANONYMIZATION_VERSION,

        "content": {
            "blocks": redacted_blocks
        },

        "redactions": redactions,

        "signals": normalized["signals"],
        "metrics": normalized["metrics"],

        "timestamps": {
            "normalized_at": timestamps["normalized_at"],
            "anonymized_at": anonymized_at.isoformat(),
        },
    }

    return anonymized
















'''
{
  "session_id": "...",
  "anonymization_version": "1.0",

  "content": {
    "blocks": {...}
  },

  "redactions": {
    "emails": [...],
    "phones": [...],
    "urls": [...]
  },

  "signals": {...},
  "metrics": {...},

  "timestamps": {
    "normalized_at": "...",
    "anonymized_at": "..."
  }
}

'''