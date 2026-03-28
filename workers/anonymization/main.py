'''
Setup logging

initialize_blob_storage()

asyncio.run(consume_messages())
'''

"""
Anonymization Worker entrypoint.

Bootstraps the process and starts the consumer loop.
"""

import sys
from pathlib import Path

# ------------------------------------------------------------
# Path bootstrapping (required for your project structure)
# ------------------------------------------------------------
project_root = Path(__file__).resolve().parent.parent.parent
backend_dir = project_root / "backend"

sys.path.insert(0, str(backend_dir))   # for backend.src.*
sys.path.insert(0, str(project_root))  # for workers.*, backend.*

# ------------------------------------------------------------
# Runtime imports
# ------------------------------------------------------------
import asyncio 
import logging

from backend.src.services.blob import initialize_blob_storage
from workers.anonymization.consumer import consume_messages


# ------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------
def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


# ------------------------------------------------------------
# Main entrypoint
# ------------------------------------------------------------
def main() -> None:
    # 1. Setup logging first
    setup_logging()

    logging.getLogger(__name__).info(
        "Starting anonymization worker",
    )

    # 2. Initialize shared infrastructure
    initialize_blob_storage()

    # NOTE:
    # DB connections are created per message in consumer

    # 3. Run consumer loop
    try:
        asyncio.run(consume_messages())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info(
            "Worker shutdown requested"
        )


# ------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------
if __name__ == "__main__":
    main()