''' THis file on a broad scales does this 
eceive ASB messages
deserialize & validate them
open DB session
call process_normalization_job
ACK / abandon / dead-letter messages correctly
handle shutdown safely
# '''

# import asyncio
# import json
# import logging
# import signal
# from contextlib import asynccontextmanager
# from collections.abc import AsyncGenerator

# from azure.servicebus.aio import ServiceBusClient
# from azure.servicebus import ServiceBusMessage
# from azure.servicebus.exceptions import ServiceBusError

# from sqlalchemy.ext.asyncio import AsyncSession

# from backend.src.db.session import get_db_sqlalchemy
# from backend.src.db.sessions import JobStatusEnum
# from backend.src.services.session_service import get_session
# from backend.src.config import AZURE_SERVICE_BUS_NORMALIZATION_QUEUE_NAME, AZURE_SERVICE_BUS_CONNECTION_STRING

# from .schemas import NormalizationJobMessage, NormalizedOutput
# from .processor import process_normalization_job
# from .errors import TransientNormalizationError, NormalizationError, PermanentNormalizationError


# QUEUE_NAME = AZURE_SERVICE_BUS_NORMALIZATION_QUEUE_NAME
# MAX_CONCURRENT_MESSAGES = 1
# POLL_TIMEOUT = 50
# NORMALIZATION_MAX_DELIVERY_COUNT = 3
# _shutdown_event = asyncio.Event()

# logger = logging.getLogger("normalization.consumer")


# def _handle_shutdown_signal() -> None:
#     logger.info("Shutdown signal received. Stopping consumer loop...")
#     _shutdown_event.set()


# def setup_signal_handlers() -> None:
#     signal.signal(signal.SIGTERM, lambda *_: _handle_shutdown_signal())
#     signal.signal(signal.SIGINT, lambda *_: _handle_shutdown_signal())

# async def _handle_message(receiver, message: ServiceBusMessage) -> None:
#     session_id = None
#     print(f"normalization consumer entered, Message: {message}")

#     try:
#         # 1. PARSE PAYLOAD
#         try:
#             payload = json.loads(str(message))
#             job = NormalizationJobMessage(**payload)
#             session_id = job.session_id
#         except Exception as e:
#             logger.error("Invalid message format, dead-lettering",
#                          extra={"error": str(e)})
#             await receiver.dead_letter_message(
#                 message,
#                 reason="InvalidPayload",
#                 error_description=str(e)
#             )
#             return  # EXIT: Message is Dead-lettered

#         logger.info(
#             "Received normalization job",
#             extra={
#                 "session_id": str(session_id),
#                 "delivery_count": message.delivery_count,
#             },
#         )

#         # 2. PROCESS JOB
#         async with get_db_session() as db:
#             await process_normalization_job(db=db, message=job)

#         # 3. SUCCESS: COMPLETE
#         await receiver.complete_message(message)
#         logger.info("Message completed successfully",
#                     extra={"session_id": str(session_id)})
#         return  # EXIT: Message is Completed

#     except Exception as e:
#         # 4. FAILURE HANDLING (Abandon or Dead-letter)
#         logger.exception(
#             "Unhandled normalization error",
#             extra={
#                 "session_id": str(session_id),
#                 "delivery_count": message.delivery_count,
#             },
#         )

#         if message.delivery_count >=NORMALIZATION_MAX_DELIVERY_COUNT:
#             logger.warning("Max retries reached, dead-lettering",
#                            extra={"session_id": str(session_id)})
#             await receiver.dead_letter_message(
#                 message,
#                 reason="MaxDeliveryExceeded",
#                 error_description=str(e),
#             )
#         else:
#             logger.warning("Transient error, abandoning for retry",
#                            extra={"session_id": str(session_id)})
#             await receiver.abandon_message(message)

#         return  # EXIT: Message is either Abandoned or Dead-lettered


# @asynccontextmanager
# async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
#     async for session in get_db_sqlalchemy():
#         try:
#             yield session
#         finally:
#             await session.close()


# async def consume_messages() -> None:
#     setup_signal_handlers()
#     logger.info("starting normalization worker consume")
#     async with ServiceBusClient.from_connection_string(
#         conn_str=AZURE_SERVICE_BUS_CONNECTION_STRING,
#         logging_enable=False
#     ) as sb_client:
#         receiver = sb_client.get_queue_receiver(
#             queue_name=QUEUE_NAME,
#             max_wait_time=POLL_TIMEOUT,
#             max_message_count=MAX_CONCURRENT_MESSAGES
#         )
#         async with receiver:
#             while not _shutdown_event.is_set():
#                 try:
#                     messages = await receiver.receive_messages()
#                     if not message:
#                         continue
#                     for message in messages:
#                         await _handle_message(receiver, message)
#                 except ServiceBusError as e:
#                     logger.exception("Service Bus error, retrying loop")
#                     await asyncio.sleep(2)
#                 except Exception:
#                     # Unexpected failure — log and keep worker alive
#                     logger.exception("Unexpected consumer error")
#                     await asyncio.sleep(1)
#     logger.info("Normalization worker consumer stopped")







# # async def _handle_message(receiver, message: ServiceBusMessage) -> None:
# #     session_id = None
# #     print("normalization consumer entered, Message: ",message)
# #     try:
# #         try:
# #             payload = json.loads(str(message))
# #             job = NormalizationJobMessage(**payload)
# #             session_id = job.session_id
# #         except Exception as e:
# #             logger.error(
# #                 "Invalid message format, dead-lettering",
# #                 extra={"error": str(e)},
# #             )
# #             await receiver.dead_letter_message(
# #                 message,
# #                 reason="InvalidPayload",
# #                 error_description=str(e),
# #             )
# #             return
# #         logger.info(
# #                 "Received normalization job",
# #                 extra={
# #                     "session_id": str(job.session_id),
# #                     "delivery_count": message.delivery_count,
# #                 },
# #             )

# #         async with get_db_session() as db:
# #             await process_normalization_job(
# #                 db=db, message=job
# #             )
# #         await receiver.complete_message(message)
# #         logger.warning(
# #             "Transient extraction error, will retry",
# #             extra={
# #                 "session_id": str(session_id),
# #                 "delivery_count": message.delivery_count,
# #                 "error": str(e)
# #             },
# #         )

# #         await receiver.abandon_message(message)
# #          #unkonwn failure, decided for retry or dlq
# #     # - If delivery_count already high → dead-letter
# #     # - Else → abandon for retry IMPLEMENT SAME SHIT FOR EXTRACTION CONSUMER
# #     except Exception as e:
# #         logger.exception(
# #             "Unhandled normalization error",
# #             extra={
# #                 "session_id": str(session_id),
# #                 "delivery_count": message.delivery_count,
# #             },
# #         )
# #         if message.delivery_count >= EXTRACTION_MAX_DELIVERY_COUNT:
# #             await receiver.dead_letter_message(
# #                 message,
# #                 reason="MaxDeliveryExceeded",
# #                 error_description=str(e),
# #             )
# #         else:
# #             await receiver.abandon_message(message)






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
    AZURE_SERVICE_BUS_NORMALIZATION_QUEUE_NAME,
    AZURE_SERVICE_BUS_CONNECTION_STRING,
)

from .schemas import NormalizationJobMessage
from .processor import process_normalization_job
from .errors import (
    TransientNormalizationError,
    PermanentNormalizationError,
)

QUEUE_NAME = AZURE_SERVICE_BUS_NORMALIZATION_QUEUE_NAME
MAX_CONCURRENT_MESSAGES = 1
POLL_TIMEOUT = 50
NORMALIZATION_MAX_DELIVERY_COUNT = 3

_shutdown_event = asyncio.Event()

logger = logging.getLogger("normalization.consumer")


def _handle_shutdown_signal() -> None:
    logger.info("Shutdown signal received. Stopping consumer loop...")
    _shutdown_event.set()


def setup_signal_handlers() -> None:
    signal.signal(signal.SIGTERM, lambda *_: _handle_shutdown_signal())
    signal.signal(signal.SIGINT, lambda *_: _handle_shutdown_signal())


async def _handle_message(receiver, message: ServiceBusMessage) -> None:
    session_id = None

    try:
        # ------------------------------------------------------------
        # 1. PARSE PAYLOAD
        # ------------------------------------------------------------
        try:
            payload = json.loads(str(message))
            job = NormalizationJobMessage(**payload)
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
            "Received normalization job",
            extra={
                "session_id": str(session_id),
                "delivery_count": message.delivery_count,
            },
        )

        # ------------------------------------------------------------
        # 2. PROCESS JOB
        # ------------------------------------------------------------
        async with get_db_session() as db:
            await process_normalization_job(db=db, message=job)

        # ------------------------------------------------------------
        # 3. SUCCESS → COMPLETE
        # ------------------------------------------------------------
        await receiver.complete_message(message)
        logger.info(
            "Message completed successfully",
            extra={"session_id": str(session_id)},
        )

    except TransientNormalizationError:
        # ------------------------------------------------------------
        # RETRYABLE FAILURE
        # ------------------------------------------------------------
        logger.warning(
            "Transient normalization error, abandoning for retry",
            extra={
                "session_id": str(session_id),
                "delivery_count": message.delivery_count,
            },
        )
        await receiver.abandon_message(message)

    except PermanentNormalizationError as e:
        # ------------------------------------------------------------
        # PERMANENT FAILURE → ACK (session already FAILED)
        # ------------------------------------------------------------
        logger.error(
            "Permanent normalization failure, completing message",
            extra={
                "session_id": str(session_id),
                "error": str(e),
            },
        )
        await receiver.complete_message(message)

    except Exception as e:
        # ------------------------------------------------------------
        # UNKNOWN FAILURE
        # ------------------------------------------------------------
        logger.exception(
            "Unhandled normalization error",
            extra={
                "session_id": str(session_id),
                "delivery_count": message.delivery_count,
            },
        )

        if message.delivery_count >= NORMALIZATION_MAX_DELIVERY_COUNT:
            logger.warning(
                "Max retries reached, dead-lettering message",
                extra={"session_id": str(session_id)},
            )
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
    logger.info("Starting normalization worker consumer")

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
                    logger.exception("Service Bus error, retrying loop")
                    await asyncio.sleep(2)

                except Exception:
                    logger.exception("Unexpected consumer error")
                    await asyncio.sleep(1)

    logger.info("Normalization worker consumer stopped")
