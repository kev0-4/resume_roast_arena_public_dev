'''
this si a long running asb service loop, this receives messages from  asb queue , deserialize,validate a payload,
calls process_extraction_job if needed
ack/abandon/dlq 
'''
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
from backend.src.db.sessions import JobStatusEnum
from backend.src.services.session_service import get_session
from backend.src.config import AZURE_SERVICE_BUS_QUEUE_NAME, AZURE_SERVICE_BUS_CONNECTION_STRING

from .schemas import ExtractionJobMessage
from .processor import process_extraction_job
from .errors import TransientExtractionError

logger = logging.getLogger("extraction.consumer")


QUEUE_NAME = AZURE_SERVICE_BUS_QUEUE_NAME
MAX_CONCURRENT_MESSAGES = 1
POLL_TIMEOUT = 50
EXTRACTION_MAX_DELIVERY_COUNT = 3
_shutdown_event = asyncio.Event()

def _handle_shutdown_signal() ->None:
    logger.info("Shutdown signal received. Stopping consumer loop...")
    _shutdown_event.set()
def setup_signal_handlers() -> None:
    signal.signal(signal.SIGTERM, lambda *_: _handle_shutdown_signal())
    signal.signal(signal.SIGINT, lambda *_: _handle_shutdown_signal())
async def _handle_message(receiver, message: ServiceBusMessage) -> None:
    session_id = None
    print("---------------------------------------------------------")
    print("---------------------------")
    print(message)
    try:
        try:
            print("entered nested try")
            payload = json.loads(str(message))
            print(payload)
            job = ExtractionJobMessage(**payload)
            session_id = job.session_id
        except Exception as e:
            logger.error(
                "Invalid message format, dead-lettering",
                extra={"error": str(e)},
            )

            await receiver.dead_letter_message(
                message,
                reason="InvalidPayload",
                error_description=str(e),
            )
            
            return
        logger.info(
                "Received extraction job",
                extra={
                    "session_id": str(job.session_id),
                    "delivery_count": message.delivery_count,
                },
            )


        async with get_db_session() as db:
            await process_extraction_job(
                db=db,
                message=job,
            )
        await receiver.complete_message(message)
        logger.info(
            "Extraction job completed",
            extra={"session_id": str(job.session_id)},
        )
    except TransientExtractionError as e: #retry-able failure
        logger.warning(
            "Transient extraction error, will retry",
            extra={
                "session_id": str(session_id),
                "delivery_count": message.delivery_count,
                "error": str(e),
            },
        )

        await receiver.abandon_message(message)


    #unkonwn failure, decided for retry or dlq
    # - If delivery_count already high → dead-letter
    # - Else → abandon for retry
    except Exception as e:
        logger.exception(
            "Unhandled extraction error",
            extra={
                "session_id": str(session_id),
                "delivery_count": message.delivery_count,
            },
        )
        if message.delivery_count >= EXTRACTION_MAX_DELIVERY_COUNT:
            await receiver.dead_letter_message(
                message,
                reason="MaxDeliveryExceeded",
                error_description=str(e),
            )
        else:
            await receiver.abandon_message(message)

@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db_sqlalchemy():
        try:
            yield session
        finally:
            await session.close()

async def consume_messages() -> None:

    setup_signal_handlers()
    logger.info("starting extraction worker consumer")

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
                except ServiceBusError as e:
                    logger.exception("Service Bus error, retrying loop")
                    await asyncio.sleep(2)
                except Exception:
                    # Unexpected failure — log and keep worker alive
                    logger.exception("Unexpected consumer error")
                    await asyncio.sleep(1)
    logger.info("Extraction worker consumer stopped")
