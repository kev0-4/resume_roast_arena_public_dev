"""
LLM Roast Worker entrypoint.

Input:  prompt/<session_id>/prompt.txt
Output: roast/<session_id>/roast.json

Flow:
  Service Bus (LLM queue)
      ↓
  consumer.py
      ↓
  processor.py
      ↓
  load prompt.txt
      ↓
  call Gemini API (gemini-3.8-flash)
      ↓
  parse VERDICT / ROAST / FIXES
      ↓
  upload roast.json
      ↓
  mark ROASTED
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import logging

from backend.src.services.blob import initialize_blob_storage
from workers.llm.consumer import consume_messages


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting LLM roast worker")

    initialize_blob_storage()

    try:
        asyncio.run(consume_messages())
    except KeyboardInterrupt:
        logger.info("LLM roast worker shutdown requested")


if __name__ == "__main__":
    main()
