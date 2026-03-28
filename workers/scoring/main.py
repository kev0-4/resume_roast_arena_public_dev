'''
Input:
anonymized.json

Output:
scored.json

Highlevel flow:
Service Bus message
   ↓
consumer.py
   ↓
processor.py
   ↓
load anonymized.json
   ↓
rules engine (signals + metrics)
   ↓
assemble scored.json
   ↓
upload blob
   ↓
mark SCORED
'''


"""
Scoring Worker entrypoint.

This file is intentionally minimal.
It only bootstraps the process and starts the consumer loop.
"""

import sys
from pathlib import Path

# ------------------------------------------------------------
# PYTHON PATH SETUP (same as other workers)
# ------------------------------------------------------------
project_root = Path(__file__).resolve().parent.parent.parent
backend_dir = project_root / "backend"

sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(project_root))

# ------------------------------------------------------------
# IMPORTS
# ------------------------------------------------------------
import asyncio
import logging

from backend.src.services.blob import initialize_blob_storage
from workers.scoring.consumer import consume_messages


# ------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------
def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def main() -> None:
    # 1. Setup logging first
    setup_logging()

    logger = logging.getLogger(__name__)
    logger.info("Starting scoring worker")

    # 2. Initialize shared infrastructure
    initialize_blob_storage()

    # 3. Start consumer loop
    try:
        asyncio.run(consume_messages())
    except KeyboardInterrupt:
        logger.info("Scoring worker shutdown requested")


# ------------------------------------------------------------
# ENTRYPOINT
# ------------------------------------------------------------
if __name__ == "__main__":
    main()