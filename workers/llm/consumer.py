"""
workers/llm/consumer.py

LLM roast worker consumer.

Responsibilities:
- Receive Service Bus messages from the LLM queue
- Deserialize and validate
- Open DB session
- Call process_llm_job
- Handle ACK / retry / DLQ
- Graceful shutdown
"""

import asyncio
import json
import logging
import signal
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage
from azure.servicebus.exceptions import ServiceBusError

from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.db.session import get_db_sqlalchemy
from backend.src.config import (
    AZURE_SERVICE_BUS_CONNECTION_STRING,
    AZURE_SERVICE_BUS_LLM_QUEUE_NAME,
)

from .schemas import LLMJobMessage
from .processor import process_llm_job
from .errors import TransientLLMError, PermanentLLMError

QUEUE_NAME = AZURE_SERVICE_BUS_LLM_QUEUE_NAME
MAX_CONCURRENT_MESSAGES = 1
POLL_TIMEOUT = 50
LLM_MAX_DELIVERY_COUNT = 3

_shutdown_event = asyncio.Event()
logger = logging.getLogger("llm.consumer")


def _handle_shutdown_signal() -> None:
    logger.info("Shutdown signal received. Stopping LLM consumer...")
    _shutdown_event.set()


def setup_signal_handlers() -> None:
    signal.signal(signal.SIGTERM, lambda *_: _handle_shutdown_signal())
    signal.signal(signal.SIGINT, lambda *_: _handle_shutdown_signal())


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db_sqlalchemy():
        try:
            yield session
        finally:
            await session.close()


async def _handle_message(receiver, message: ServiceBusMessage) -> None:
    session_id = None

    try:
        # 1. Deserialize
        try:
            payload = json.loads(str(message))
            job = LLMJobMessage(**payload)
            session_id = job.session_id
        except Exception as e:
            logger.error("Invalid LLM job payload, dead-lettering", extra={"error": str(e)})
            await receiver.dead_letter_message(
                message,
                reason="InvalidPayload",
                error_description=str(e),
            )
            return

        logger.info(
            "Received LLM roast job",
            extra={
                "session_id": str(session_id),
                "delivery_count": message.delivery_count,
            },
        )

        # 2. Process
        async with get_db_session() as db:
            await process_llm_job(db=db, message=job)

        # 3. Success → COMPLETE
        await receiver.complete_message(message)
        logger.info("LLM roast completed successfully", extra={"session_id": str(session_id)})

    except PermanentLLMError as e:
        logger.warning(
            "Permanent LLM error, dead-lettering",
            extra={"session_id": str(session_id), "error": str(e)},
        )
        await receiver.dead_letter_message(
            message,
            reason="PermanentFailure",
            error_description=str(e),
        )

    except TransientLLMError as e:
        logger.warning(
            "Transient LLM error",
            extra={
                "session_id": str(session_id),
                "delivery_count": message.delivery_count,
                "error": str(e),
            },
        )
        if message.delivery_count >= LLM_MAX_DELIVERY_COUNT:
            await receiver.dead_letter_message(
                message,
                reason="MaxDeliveryExceeded",
                error_description=str(e),
            )
        else:
            await receiver.abandon_message(message)

    except Exception as e:
        logger.exception(
            "Unexpected LLM consumer error",
            extra={
                "session_id": str(session_id),
                "delivery_count": message.delivery_count,
            },
        )
        if message.delivery_count >= LLM_MAX_DELIVERY_COUNT:
            await receiver.dead_letter_message(
                message,
                reason="UnknownFailure",
                error_description=str(e),
            )
        else:
            await receiver.abandon_message(message)


async def consume_messages() -> None:
    setup_signal_handlers()
    logger.info("Starting LLM roast consumer")

    async with ServiceBusClient.from_connection_string(
        conn_str=AZURE_SERVICE_BUS_CONNECTION_STRING,
        logging_enable=False,
    ) as sb_client:

        receiver = sb_client.get_queue_receiver(
            queue_name=QUEUE_NAME,
            max_wait_time=POLL_TIMEOUT,
            max_message_count=MAX_CONCURRENT_MESSAGES,
        )

        async with receiver:
            while not _shutdown_event.is_set():
                try:
                    messages = await receiver.receive_messages()
                    if not messages:
                        continue
                    for message in messages:
                        await _handle_message(receiver, message)

                except ServiceBusError:
                    logger.exception("Service Bus error, retrying...")
                    await asyncio.sleep(2)

                except Exception:
                    logger.exception("Unexpected consumer loop error")
                    await asyncio.sleep(1)

    logger.info("LLM consumer stopped")
