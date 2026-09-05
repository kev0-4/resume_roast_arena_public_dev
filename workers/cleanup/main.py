"""
Cleanup Worker entrypoint.

Not a Service-Bus consumer like every other worker in this repo -- this is
a periodic sweep, not message-driven. Runs both TTL sweeps (sweep.py) on a
loop, sleeping CLEANUP_SWEEP_INTERVAL_SECONDS between passes.

Flow:
  loop:
    open DB session
    cleanup_raw_uploads()        -- delete raw/<id>/ blobs older than 24h
    cleanup_expired_anonymous_sessions()  -- delete whole sessions (row + all
                                              blobs) for anon users older than 30d
    sleep(CLEANUP_SWEEP_INTERVAL_SECONDS)
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import logging

from backend.src.services.blob import initialize_blob_storage
from backend.src.db.session import get_db_sqlalchemy
from backend.src.config import CLEANUP_SWEEP_INTERVAL_SECONDS

from .sweep import cleanup_raw_uploads, cleanup_expired_anonymous_sessions

_shutdown_event = asyncio.Event()


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def run_sweep_once() -> None:
    logger = logging.getLogger(__name__)
    async for db in get_db_sqlalchemy():
        try:
            raw_count = await cleanup_raw_uploads(db)
            anon_count = await cleanup_expired_anonymous_sessions(db)
            logger.info(
                "Cleanup sweep complete",
                extra={"raw_deleted": raw_count, "sessions_deleted": anon_count},
            )
        finally:
            await db.close()


async def consume_sweeps() -> None:
    logger = logging.getLogger(__name__)
    logger.info("Starting cleanup worker")
    while not _shutdown_event.is_set():
        try:
            await run_sweep_once()
        except Exception:
            logger.exception("Cleanup sweep failed, will retry next interval")
        await asyncio.sleep(CLEANUP_SWEEP_INTERVAL_SECONDS)


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting cleanup worker")

    initialize_blob_storage()

    try:
        asyncio.run(consume_sweeps())
    except KeyboardInterrupt:
        logger.info("Cleanup worker shutdown requested")


if __name__ == "__main__":
    main()
