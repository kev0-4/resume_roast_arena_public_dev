"""
Renderer Worker entrypoint.

Input:  scored/<session_id>/scored.json + roast/<session_id>/roast.json
Output: render/<session_id>/render.png

Flow:
  Service Bus (render queue)
      ↓
  consumer.py
      ↓
  processor.py
      ↓
  load scored.json + roast.json
      ↓
  compute composite score + stamp
      ↓
  render HTML → screenshot PNG (Playwright)
      ↓
  upload render.png
      ↓
  mark DONE
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
backend_dir = project_root / "backend"

sys.path.insert(0, str(backend_dir))  # backend/src/__init__.py does `from src...` (absolute), needs backend/ on sys.path
sys.path.insert(0, str(project_root))

import asyncio
import logging

from backend.src.services.blob import initialize_blob_storage
from workers.renderer.consumer import consume_messages


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting renderer worker")

    initialize_blob_storage()

    try:
        asyncio.run(consume_messages())
    except KeyboardInterrupt:
        logger.info("Renderer worker shutdown requested")


if __name__ == "__main__":
    main()
