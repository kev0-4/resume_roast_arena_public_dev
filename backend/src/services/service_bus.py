'''
this module connects to ASB , maintains queue, passes on messages to ASB
!! QUEUE CANNOT EB CREATED VIA ADMIN CLIENT CAUSE OF SSL RULES, NEED TO MANUALLY CREATE WHEN DEPLOYING
'''
import asyncio
from azure.servicebus import ServiceBusClient, ServiceBusMessage
import json
import logging
from datetime import datetime
from ..config import AZURE_SERVICE_BUS_CONNECTION_STRING, AZURE_SERVICE_BUS_QUEUE_NAME, AZURE_SERVICE_BUS_NORMALIZATION_QUEUE_NAME
from ..utils.telemetry import emit_event


_CONNECTION_STRING = AZURE_SERVICE_BUS_CONNECTION_STRING
_QUEUE_NAME = AZURE_SERVICE_BUS_QUEUE_NAME
if not _CONNECTION_STRING:
    raise RuntimeError("AZURE_SERVICE_BUS_CONNECTION_STRING is not set")

if not _QUEUE_NAME:
    raise RuntimeError("AZURE_SERVICE_BUS_QUEUE_NAME is not set")

_servicebus_client = ServiceBusClient.from_connection_string(
    conn_str=_CONNECTION_STRING, logging_enable=True
)

# _admin_client = ServiceBusAdministrationClient.from_connection_string(
#     conn_str=_CONNECTION_STRING
# )
# No need for this as having ssl error, created a bus manually and entered its name in env


class ServiceBusEnqueueError(Exception):
    pass


def enqueue_extraction(session_id: str, raw_blob_path: str) -> None:
    payload = {
        "version": "1.0",
        "job_type": "Extraction",
        "session_id": session_id,
        "raw_blob_path": raw_blob_path,
        "attempt": 1,
        "created_at": datetime.utcnow().isoformat()
    }

    try:
        message = ServiceBusMessage(
            json.dumps(payload),
            message_id=session_id,
            content_type="application/json"
        )

        emit_event(
            "servicebus.message.created",
            {
                "session_id": session_id,
                "blob_path": raw_blob_path,
                "queue_name": _QUEUE_NAME,
                "attempt": 1,
                "reason": "extraction message prepared for queue",
                "status": "INFO"
            }
        )

        with _servicebus_client.get_queue_sender(queue_name=_QUEUE_NAME) as sender:
            sender.send_messages(message)

        emit_event(
            "servicebus.enqueue.success",
            {
                "session_id": session_id,
                "blob_path": raw_blob_path,
                "queue_name": _QUEUE_NAME,
                "message_id": session_id,
                "reason": "extraction task successfully enqueued to service bus",
                "status": "INFO"
            }
        )

        logging.info(
            "Enqueued extraction task",
            extra={
                "session_id": session_id,
                "queue": _QUEUE_NAME
            }
        )

    except Exception as exc:
        emit_event(
            "servicebus.enqueue.failure",
            {
                "session_id": session_id,
                "blob_path": raw_blob_path,
                "queue_name": _QUEUE_NAME,
                "reason": f"failed to enqueue extraction task: {str(exc)}",
                "error_type": type(exc).__name__,
                "status": "ERROR"
            }
        )

        logging.exception(
            "Failed to enqueue extraction task",
            extra={"session_id": session_id}
        )
        raise ServiceBusEnqueueError(
            f"Failed to enqueue session {session_id}"
        ) from exc


def enqueue_normalization(session_id: str, extracted_blob_path: str) -> None:
    payload = {
        "version": "1.0",
        "job_type": "Normalization",
        "session_id": session_id,
        "extracted_blob_path": extracted_blob_path,
        "attempt": 1,
        "created_at": datetime.utcnow().isoformat()
    }

    try:
        message = ServiceBusMessage(
            json.dumps(payload),
            message_id=f"normalize-{session_id}",
            content_type="application/json"
        )

        emit_event(
            "servicebus.message.created",
            {
                "session_id": session_id,
                "blob_path": extracted_blob_path,
                "queue_name": AZURE_SERVICE_BUS_NORMALIZATION_QUEUE_NAME,
                "attempt": 1,
                "reason": "normalization message prepared for queue",
                "status": "INFO"
            }
        )

        with _servicebus_client.get_queue_sender(
            queue_name=AZURE_SERVICE_BUS_NORMALIZATION_QUEUE_NAME
        ) as sender:
            sender.send_messages(message)

        emit_event(
            "servicebus.enqueue.success",
            {
                "session_id": session_id,
                "blob_path": extracted_blob_path,
                "queue_name": AZURE_SERVICE_BUS_NORMALIZATION_QUEUE_NAME,
                "message_id": message.message_id,
                "reason": "normalization task successfully enqueued",
                "status": "INFO"
            }
        )

        logging.info(
            "Enqueued normalization task",
            extra={
                "session_id": session_id,
                "queue": AZURE_SERVICE_BUS_NORMALIZATION_QUEUE_NAME
            }
        )

    except Exception as exc:
        emit_event(
            "servicebus.enqueue.failure",
            {
                "session_id": session_id,
                "blob_path": extracted_blob_path,
                "queue_name": AZURE_SERVICE_BUS_NORMALIZATION_QUEUE_NAME,
                "reason": f"failed to enqueue normalization task: {str(exc)}",
                "error_type": type(exc).__name__,
                "status": "ERROR"
            }
        )

        logging.exception(
            "Failed to enqueue normalization task",
            extra={"session_id": session_id}
        )
        raise ServiceBusEnqueueError(
            f"Failed to enqueue normalization for session {session_id}"
        ) from exc
