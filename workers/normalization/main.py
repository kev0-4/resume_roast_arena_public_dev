"""
IMPORT ORDER MATTERS, PRETTIER MESSES IT UP ON CLTR+S
Normalization Worker entrypoint.

This file is intentionally minimal.
It only bootstraps the process and starts the consumer loop.
"""

import asyncio
import logging
import sys
from pathlib import Path

# ------------------------------------------------------------
# Path bootstrapping
# ------------------------------------------------------------
project_root = Path(__file__).resolve().parent.parent.parent
backend_dir = project_root / "backend"

sys.path.insert(0, str(backend_dir))   # for backend.src.*
sys.path.insert(0, str(project_root))  # for backend.*, workers.*

# ------------------------------------------------------------
# Runtime imports
# ------------------------------------------------------------


from workers.normalization.consumer import consume_messages
from backend.src.services.blob import initialize_blob_storage



def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    # 1. Logging first
    setup_logging()

    logging.getLogger(__name__).info(
        "Starting normalization worker",
    )

    # 2. Initialize shared infrastructure
    initialize_blob_storage()

    # NOTE:
    # DB connections are opened lazily per message.
    # No explicit DB init here.

    # 3. Run consumer loop
    try:
        asyncio.run(consume_messages())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Worker shutdown requested")


if __name__ == "__main__":
    main()
