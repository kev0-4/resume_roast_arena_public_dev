"""
workers/renderer/pipeline/loader.py

Loads the upstream scored.json and roast.json artifacts from Blob storage.
"""

import json
from typing import Dict, Any

from backend.src.services.blob import read_blob


def load_scored(blob_path: str) -> Dict[str, Any]:
    return json.loads(read_blob(blob_path).decode("utf-8"))


def load_roast(blob_path: str) -> Dict[str, Any]:
    return json.loads(read_blob(blob_path).decode("utf-8"))
