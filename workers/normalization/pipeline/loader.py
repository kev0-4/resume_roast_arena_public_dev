'''
Docstring for workers.normalization.pipeline.loader
Load extracted/<session_id>/extracted.json
Validate minimum required shape
Return a trusted dict to downstream pipeline stages
'''
import json
from typing import Any, Dict

from backend.src.services.blob import read_blob
from ..errors import (
    TransientNormalizationError,
    PermanentNormalizationError,
)
REQUIRED_TOP_LEVEL_FIELDS = {
    "session_id",
    "raw_text",
    "extraction_version",
    "source",
    "timestamps",
}

def load_extracted(blob_path: str) -> dict:
    #     Load and validate extracted.json.
    try:
        raw_bytes =  read_blob(blob_path)
    except Exception as e:
        raise TransientNormalizationError(
            f"Failed to read extracted blob: {e}"
        )
    

    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except Exception as e:
        raise PermanentNormalizationError(
            f"Invalid JSON in extracted artifact: {e}"
        )
    
    if not isinstance(payload, dict):
        raise PermanentNormalizationError(
            "Extracted artifact is not a JSON object"
        )


    missing_fields = REQUIRED_TOP_LEVEL_FIELDS - payload.keys()
    if missing_fields:
        raise PermanentNormalizationError(
            f"Extracted artifact missing fields: {missing_fields}"
        )
    
    raw_text = payload.get("raw_text")

    if not isinstance(raw_text, str):
        raise PermanentNormalizationError(
            "raw_text must be a string"
        )
    
    return payload

