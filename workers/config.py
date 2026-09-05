import os
from dotenv import load_dotenv, dotenv_values
from backend.src.utils.telemetry import emit_event
load_dotenv()
VALUES = config = dotenv_values(".env")
SECRET_KEY = os.getenv("SECRET_KEY")

POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DATABASE_URL = os.getenv("DATABASE_URL")

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_URL = os.getenv("REDIS_URL")


AZURE_STORAGE_ACCOUNT = os.getenv("AZURE_STORAGE_ACCOUNT")
AZURE_STORAGE_KEY = os.getenv("AZURE_STORAGE_KEY")
AZURE_BLOB_ENDPOINT = os.getenv("AZURE_BLOB_ENDPOINT")
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")
AZURE_CONTAINER_RAW_FOLDER_PREFIX = os.getenv(
    "AZURE_CONTAINER_RAW_FOLDER_PREFIX")
AZURE_SERVICE_BUS_CONNECTION_STRING = os.getenv(
    "AZURE_SERVICE_BUS_CONNECTION_STRING")
AZURE_SERVICE_BUS_QUEUE_NAME = os.getenv("AZURE_SERVICE_BUS_QUEUE_NAME")

TIKA_SERVER_ENDPOINT=os.getenv("TIKA_SERVER_ENDPOINT")


if None in VALUES:
    # Deliberately not logging VALUES itself -- it can contain secrets
    # (SECRET_KEY, passwords), and emit_event persists to log_entry.json
    # rather than a transient console print.
    emit_event(
        "worker_config.env_check_warning",
        {"reason": "one or more expected variables not found in .env", "status": "WARNING"},
    )
