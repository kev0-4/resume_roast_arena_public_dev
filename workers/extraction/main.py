# import asyncio
# import logging

# async def consume_messages() -> None:
#     """
#     Long-running ASB receive loop.
#     """

#     # TODO:
#     # - initialize ServiceBusClient
#     # - create receiver for 'resume-extraction' queue

#     while True:
#         # TODO:
#         # - receive message
#         # - parse JSON
#         # - validate using ExtractionJobMessage
#         # - open DB session
#         # - call process_extraction_job
#         # - complete or abandon message
#         pass





"""
Extraction Worker entrypoint.

This file is intentionally minimal.
It only bootstraps the process and starts the consumer loop.
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
backend_dir = project_root / "backend"

sys.path.insert(0, str(backend_dir))  # So backend's "from src..." works
sys.path.insert(0, str(project_root))  # So "from backend..." and "from workers..." work

import asyncio
import logging


#import backend.src.config 
from backend.src.services.blob import initialize_blob_storage
from workers.extraction.consumer import consume_messages


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    # 1. Logging first (so startup errors are visible)
    setup_logging()

    logging.getLogger(__name__).info(
        "Starting extraction worker",
    )

    # 2. Initialize shared infrastructure
    initialize_blob_storage()

    # NOTE:
    # DB connections are opened lazily per message,
    # so no DB init needed here.

    # 3. Run consumer loop
    try:
        asyncio.run(consume_messages())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Worker shutdown requested")


if __name__ == "__main__":
    main()
