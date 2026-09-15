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
# Scoring only. The interview itself no longer runs through this model --
# the browser talks to GEMINI_LIVE_MODEL directly -- so this is now used
# for exactly one call per interview, at the end, over the transcript.
GEMINI_INTERVIEW_MODEL = os.getenv("GEMINI_INTERVIEW_MODEL", GEMINI_ROAST_MODEL)

# The real-time voice model the browser connects to over WebSocket. Named
# explicitly rather than defaulting to the roast model: only the *-live-*
# models accept bidiGenerateContent at all.
GEMINI_LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")

# The interviewer's voice is chosen PER INTERVIEW and then pinned for the
# whole of it.
#
# Without pinning, the API picks a voice per session, and a multi-round
# interview opens several -- so the interviewer audibly became a different
# person after the coding round. Pinning one global voice fixes that but
# makes every interview sound identical, which is worse for a product
# people run repeatedly. Deriving it from the interview id gives both: a
# different interviewer each time, the same one throughout.
#
# All 20 verified accepted by gemini-3.1-flash-live-preview -- an invalid
# name would break every interview unlucky enough to draw it, and would
# present as a dead session rather than a config error.
GEMINI_LIVE_VOICES = tuple(
    v.strip()
    for v in os.getenv(
        "GEMINI_LIVE_VOICES",
        "Puck,Charon,Kore,Fenrir,Aoede,Leda,Orus,Zephyr,Autonoe,Callirrhoe,"
        "Enceladus,Iapetus,Umbriel,Algieba,Despina,Erinome,Laomedeia,Schedar,"
        "Achird,Sadachbia",
    ).split(",")
    if v.strip()
)

# Ephemeral-token lifetimes, both deliberately short.
#
# NEW_SESSION is the window in which the browser must OPEN its socket; once
# open, EXPIRE is when the session is cut off regardless. The gap between
# them is the hard cap on interview length, which also sits just inside the
# Live API's own ~10-minute connection lifetime, so a session never has to
# be resumed mid-interview.
#
# These two plus uses=1 are the ONLY real protections on a minted token.
# live_connect_constraints is advisory: a token minted for this model was
# verified to open a session on a different, pricier one. Blast radius is
# therefore one session per token, which is why the window is this tight.
INTERVIEW_TOKEN_NEW_SESSION_SECONDS = int(os.getenv("INTERVIEW_TOKEN_NEW_SESSION_SECONDS", "120"))
INTERVIEW_TOKEN_EXPIRE_SECONDS = int(os.getenv("INTERVIEW_TOKEN_EXPIRE_SECONDS", "660"))

# Per-chunk client telemetry from the live interview: audio timings, socket
# state, why a turn stalled. Invaluable while debugging a live call, far too
# noisy to run in production -- it prints on every transcript chunk, which is
# several times a second for the length of an interview. Off unless asked for.
INTERVIEW_DIAG_LOG = os.getenv("INTERVIEW_DIAG_LOG", "false").lower() == "true"

INGEST_RATE_LIMIT_MAX = int(os.getenv("INGEST_RATE_LIMIT_MAX", "5"))
INGEST_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("INGEST_RATE_LIMIT_WINDOW_SECONDS", "3600"))

# The one interview rate limit that still exists. There is no per-turn
# limit any more because there are no turns -- a live session's cost is
# bounded by the token's own expiry, so capping how many sessions a user
# can START is the only lever that matters.
#
# One per week while the feature is free and unproven: a Live session is
# by far the most expensive thing this app does per user. This is a
# placeholder for entitlements, not a permanent design -- when a paid tier
# exists, the cap belongs on the account's plan rather than in config.
INTERVIEW_START_RATE_LIMIT_MAX = int(os.getenv("INTERVIEW_START_RATE_LIMIT_MAX", "1"))
INTERVIEW_START_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("INTERVIEW_START_RATE_LIMIT_WINDOW_SECONDS", "604800"))

# Admin accounts, comma-separated and matched case-insensitively.
#
# "Admin" here means exactly ONE thing today: exempt from the interview
# rate limit, so the feature stays testable without waiting a week between
# runs. It grants no other privilege, and nothing should start treating it
# as a general permission without that being a deliberate decision -- an
# email list is authentication by claim, which is fine for skipping a
# counter and not fine for anything that reads or writes someone's data.
#
# Deliberately config rather than a hardcoded check: changeable without
# shipping code, and an obvious single place to delete once real
# entitlements exist.
ADMIN_EMAILS = frozenset(
    email.strip().lower()
    for email in os.getenv(
        "ADMIN_EMAILS", "kevintandon123@gmail.com,lemonocean11@gmail.com"
    ).split(",")
    if email.strip()
)

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
