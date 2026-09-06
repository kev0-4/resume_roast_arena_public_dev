import os
from dotenv import load_dotenv, dotenv_values
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
# Local docker-compose Redis has no TLS; managed providers (Upstash, Azure
# Cache for Redis) require it. Off by default so local dev is unaffected.
REDIS_SSL = os.getenv("REDIS_SSL", "false").lower() == "true"


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
AZURE_SERVICE_BUS_NORMALIZATION_QUEUE_NAME = os.getenv("AZURE_SERVICE_BUS_NORMALIZATION_QUEUE_NAME")
AZURE_SERVICE_BUS_ANONYMIZATION_QUEUE_NAME= os.getenv("AZURE_SERVICE_BUS_ANONYMIZATION_QUEUE_NAME")
AZURE_SERVICE_BUS_SCORING_QUEUE_NAME = os.getenv("AZURE_SERVICE_BUS_SCORING_QUEUE_NAME")
AZURE_SERVICE_BUS_LLM_QUEUE_NAME = os.getenv("AZURE_SERVICE_BUS_LLM_QUEUE_NAME")
AZURE_SERVICE_BUS_RENDER_QUEUE_NAME = os.getenv("AZURE_SERVICE_BUS_RENDER_QUEUE_NAME")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_ROAST_MODEL = os.getenv("GEMINI_ROAST_MODEL", "gemini-3.5-flash-lite")

INGEST_RATE_LIMIT_MAX = int(os.getenv("INGEST_RATE_LIMIT_MAX", "5"))
INGEST_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("INGEST_RATE_LIMIT_WINDOW_SECONDS", "3600"))

RAW_UPLOAD_TTL_HOURS = int(os.getenv("RAW_UPLOAD_TTL_HOURS", "24"))
ANONYMOUS_ROAST_TTL_DAYS = int(os.getenv("ANONYMOUS_ROAST_TTL_DAYS", "30"))
CLEANUP_SWEEP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_SWEEP_INTERVAL_SECONDS", "3600"))

# Comma-separated list of origins allowed to call this API from a browser.
# Defaults to the Next.js dev server -- no frontend existed when this API
# was first built, so nothing set this before now.
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

if None in VALUES:
    print("Warning: one or more variables not found in environment variables.")
    print(VALUES)  # comment out later
