# tests/test_service_bus_consumer.py
"""
Run this script to listen for messages on the Service Bus queue.
Usage: python -m tests.test_service_bus_consumer
"""
import asyncio
from azure.servicebus.aio import ServiceBusClient
import json
import logging

AZURE_SERVICE_BUS_CONNECTION_STRING="Endpoint=sb://localhost;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=SAS_KEY_VALUE;UseDevelopmentEmulator=true;"
AZURE_SERVICE_BUS_QUEUE_NAME="myServiceBusQueue"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def receive_messages():
    """
    Receive and print messages from Service Bus queue.
    Press Ctrl+C to stop.
    """
    servicebus_client = ServiceBusClient.from_connection_string(
        conn_str=AZURE_SERVICE_BUS_CONNECTION_STRING,
        logging_enable=True
    )
    
    async with servicebus_client:
        receiver = servicebus_client.get_queue_receiver(
            queue_name=AZURE_SERVICE_BUS_QUEUE_NAME
        )
        
        async with receiver:
            logger.info(f"📡 Listening for messages on queue: {AZURE_SERVICE_BUS_QUEUE_NAME}")
            logger.info("Press Ctrl+C to stop...\n")
            
            async for msg in receiver:
                try:
                    # Parse message body
                    body = str(msg)
                    payload = json.loads(body)
                    
                    logger.info("=" * 60)
                    logger.info("📨 MESSAGE RECEIVED")
                    logger.info(f"Message ID: {msg.message_id}")
                    logger.info(f"Session ID: {payload.get('session_id')}")
                    logger.info(f"Blob Path: {payload.get('raw_blob_path')}")
                    logger.info(f"Attempt: {payload.get('attempt')}")
                    logger.info(f"Created At: {payload.get('created_at')}")
                    logger.info(f"Full Payload: {json.dumps(payload, indent=2)}")
                    logger.info("=" * 60 + "\n")
                    
                    # Complete the message (removes it from queue)
                    await receiver.complete_message(msg)
                    logger.info("✅ Message completed (removed from queue)\n")
                    
                except json.JSONDecodeError:
                    logger.error(f"❌ Failed to parse message: {body}")
                    await receiver.dead_letter_message(msg, reason="Invalid JSON")
                    
                except Exception as e:
                    logger.exception(f"❌ Error processing message: {e}")
                    # Abandon message (returns to queue for retry)
                    await receiver.abandon_message(msg)

if __name__ == "__main__":
    try:
        asyncio.run(receive_messages())
    except KeyboardInterrupt:
        print("\n👋 Stopped listening for messages")