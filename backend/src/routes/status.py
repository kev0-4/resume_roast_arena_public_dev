'''
This route has health and ready checkpoints
also has their supporting util functions, to check connectivity with postgres, redis, azure blob

Two endpoints, deliberately separate:

  GET /health/          -- can this service reach its dependencies?
  GET /health/pipeline  -- is work actually flowing through the pipeline?

They answer different questions and must not be merged. The first says
nothing about whether roasts are completing: the backend can reach Postgres,
Redis and Blob perfectly while a worker is dead and every upload sits
half-finished forever. That was the real gap -- a dead worker reported green.

The split also matters operationally. /health/ is the shape a container
liveness probe wants, and a probe that fails because a *different* service
is stuck would restart the wrong thing. /health/pipeline is for the external
watchdog (.github/workflows/watchdog.yml), never for a probe.
'''
from fastapi import APIRouter, Depends, Response, status
import psycopg2
from src.config import POSTGRES_DB, POSTGRES_HOST, POSTGRES_PASSWORD, POSTGRES_PORT, POSTGRES_USER
from src.config import REDIS_HOST, REDIS_PORT, REDIS_URL, REDIS_PASSWORD, REDIS_SSL
from src.config import AZURE_BLOB_ENDPOINT, AZURE_STORAGE_ACCOUNT, AZURE_STORAGE_CONNECTION_STRING, AZURE_STORAGE_KEY
import time
from datetime import datetime, timedelta

import redis
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError, AzureError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db_sqlalchemy
from src.db.sessions import Sessions
from src.utils.telemetry import emit_event

status_router = APIRouter(
    prefix="/health"
)

# A session in any other status is mid-flight and something should still be
# moving it along.
TERMINAL_STATUSES = ("DONE", "FAILED")

# How long a session may sit in one non-terminal status before we call it
# stuck. Generous on purpose: the whole pipeline is normally well under a
# minute, so 30 minutes cannot be confused with "busy".
STUCK_AFTER_MINUTES = 30

# Below this we stay green. One wedged session is a curiosity -- a user
# closing a tab mid-upload can leave one behind. Several at once is a worker
# down, which is what we want to be told about.
STUCK_TOLERATED = 3


@status_router.get("/", summary="checks health of connected services")
def health_check(response: Response):
    overall_start_time = time.perf_counter()
    res_pg = postgres_status()
    res_rd = redis_status()
    res_az = azure_status()
    total_time_taken = time.perf_counter() - overall_start_time
    entities = [
        {
            "alias": "postgres db",
            "status": res_pg['status'],
            "time_taken_seconds": res_pg['time_taken_seconds'],
            "details": res_pg.get('error') if res_pg.get('error') else 'Postgress database : Up and running , no errors'
        },
        {
            "alias": "redis",
            "status": res_rd['status'],
            "time_taken_seconds": res_rd['time_taken_seconds'],
            "details": res_rd.get('error') if res_rd.get('error') else 'Redis Cache : Up and running , no errors'
        },
        {
            "alias": "azure blob storage",
            "status": res_az['status'],
            "time_taken_seconds": res_az['time_taken_seconds'],
            "details": res_az.get('error')  if res_az.get('error') else 'Azure blob : Up and running , no errors'
        }
    ]
    overall_healthy = res_pg['healthy'] and res_rd['healthy'] and res_az['healthy']
    res = {
        "status": "Healthy" if overall_healthy else "Unhealthy",
        "totaltime_taken_seconds": total_time_taken,
        "entities": entities
    }

    if overall_healthy:
        response.status_code = status.HTTP_200_OK
    else:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        
    return res

@status_router.get("/pipeline", summary="is work actually flowing through the pipeline")
async def pipeline_health(
    response: Response,
    db: AsyncSession = Depends(get_db_sqlalchemy),
):
    """
    Report sessions that have sat in a non-terminal status too long.

    This detects a dead or wedged worker without needing the workers to
    report anything about themselves. A heartbeat can lie -- a process can be
    alive with its consumer loop wedged, and it would still tick. Work not
    moving cannot lie.

    It also localises the fault for free: the status the sessions are stuck
    IN names the stage that stopped. A pile of SCORING means the scoring
    worker; a pile of ROASTING means the LLM worker.

    Returns 200 when healthy, 503 when stuck_total exceeds STUCK_TOLERATED,
    so the watchdog needs no JSON parsing to decide -- but the body carries
    the breakdown for whoever reads the alert.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=STUCK_AFTER_MINUTES)

    started = time.perf_counter()
    try:
        result = await db.execute(
            select(Sessions.status, func.count())
            .where(Sessions.status.notin_(TERMINAL_STATUSES))
            .where(Sessions.updated_at < cutoff)
            .group_by(Sessions.status)
        )
        stuck_by_status = {row[0]: row[1] for row in result.all()}
    except Exception as e:
        # The watchdog must be able to tell "pipeline is stuck" apart from
        # "I could not find out", so this is its own status, not a false
        # green and not a false alarm.
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        emit_event("health.pipeline_check_failed", {"error": str(e)})
        return {
            "status": "Unknown",
            "detail": "could not query session state",
            "error": str(e),
            "checked_at": datetime.utcnow().isoformat(),
        }

    stuck_total = sum(stuck_by_status.values())
    healthy = stuck_total <= STUCK_TOLERATED

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        # Logged as well as returned: the alert email says "something is
        # wrong", the log says what, and now actually reaches Log Analytics.
        emit_event("health.pipeline_stuck", {
            "status": "ERROR",
            "stuck_total": stuck_total,
            "stuck_by_status": stuck_by_status,
            "threshold_minutes": STUCK_AFTER_MINUTES,
        })

    return {
        "status": "Healthy" if healthy else "Degraded",
        "stuck_total": stuck_total,
        "stuck_by_status": stuck_by_status,
        "likely_stalled_stage": (
            max(stuck_by_status, key=stuck_by_status.get) if stuck_by_status else None
        ),
        "threshold_minutes": STUCK_AFTER_MINUTES,
        "tolerated": STUCK_TOLERATED,
        "query_time_seconds": round(time.perf_counter() - started, 4),
        "checked_at": datetime.utcnow().isoformat(),
    }


def postgres_status():
    try:
        start_time = time.perf_counter()
        conn = psycopg2.connect(dbname=POSTGRES_DB, user=POSTGRES_USER,
                                host=POSTGRES_HOST, password=POSTGRES_PASSWORD,
                                port=POSTGRES_PORT)
        conn.close()
        process_time = time.perf_counter() - start_time
        return {
            "status": "healthy",
            "time_taken_seconds": process_time,
            "healthy": True
        }
    except:
        return {
            "status": "unhealthy",
            "time_taken_seconds": 00,
            "healthy": False
        }


def redis_status():
    start_time = time.perf_counter()
    try:
        r = redis.StrictRedis(
            host=REDIS_HOST, port=REDIS_PORT,
            password=REDIS_PASSWORD if REDIS_PASSWORD else None,
            socket_timeout=1,
            ssl=REDIS_SSL,
        )
        r.ping()
        process_time = time.perf_counter() - start_time

        return {
            "status": "healthy",
            "time_taken_seconds": process_time,
            "healthy": True
        }
    except redis.exceptions.ConnectionError as e:
        process_time = time.perf_counter() - start_time
        return {
            "status": "unhealthy",
            "time_taken_seconds": process_time,
            "healthy": False,
            "error": f"ConnectionError: {e}"
        }
    except Exception as e:
        process_time = time.perf_counter() - start_time
        return {
            "status": "unhealthy",
            "time_taken_seconds": process_time,
            "healthy": False,
            "error": f"Unexpected error: {e}"
        }


def azure_status():
    start_time = time.perf_counter()
    try:
        blob_service_client = BlobServiceClient.from_connection_string(
            AZURE_STORAGE_CONNECTION_STRING)
        print(blob_service_client.list_containers(max_results=1))
        process_time = time.perf_counter() - start_time

        return {
            "status": "healthy",
            "time_taken_seconds": process_time,
            "healthy": True
        }
    except (AzureError, ConnectionError, ResourceNotFoundError,Exception) as e:
        process_time = time.perf_counter() - start_time

        return {
            "status": "unhealthy",
            "time_taken_seconds": process_time,
            "healthy": False,
            "error": e
        }
