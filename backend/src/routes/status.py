'''
This route has health and ready checkpoints
also has their supporting util functions, to check connectivity with postgres, redis, azure blob
'''
from fastapi import APIRouter, Response, status
import psycopg2
from src.config import POSTGRES_DB, POSTGRES_HOST, POSTGRES_PASSWORD, POSTGRES_PORT, POSTGRES_USER
from src.config import REDIS_HOST, REDIS_PORT, REDIS_URL, REDIS_PASSWORD
from src.config import AZURE_BLOB_ENDPOINT, AZURE_STORAGE_ACCOUNT, AZURE_STORAGE_CONNECTION_STRING, AZURE_STORAGE_KEY
import time
import redis
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError, AzureError
status_router = APIRouter(
    prefix="/health"
)


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
            socket_timeout=1
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
