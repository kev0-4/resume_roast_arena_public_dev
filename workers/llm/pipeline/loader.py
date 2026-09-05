"""
workers/llm/pipeline/loader.py

Loads the prompt artifact from blob storage.
"""

from backend.src.services.blob import read_blob


def load_prompt(blob_path: str) -> str:
    """Read prompt.txt blob and return as a string."""
    raw: bytes = read_blob(blob_path)
    return raw.decode("utf-8")
