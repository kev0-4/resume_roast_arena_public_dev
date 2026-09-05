'''
Rate limiting dependency for /ingest -- per-IP for anonymous requests,
per-user for authenticated ones (there's no stable identity to key an
anonymous "session" on across requests -- every unauthenticated /ingest
gets a brand-new generated user, see utils/anon_identity.py -- so IP is
the only stable anonymous identifier available).

Fixed-window counter in Redis (INCR + EXPIRE). Fails OPEN if Redis is
unreachable: this is abuse/cost control, not a security boundary, and a
Redis outage taking down ingest entirely would be a worse failure mode
than temporarily allowing unlimited requests.
'''

import logging
from typing import Optional, Tuple

import redis
from fastapi import Request, HTTPException, status, Depends

from ..config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_PASSWORD,
    INGEST_RATE_LIMIT_MAX,
    INGEST_RATE_LIMIT_WINDOW_SECONDS,
)
from ..dependencies.auth import get_current_user_optional
from ..utils.telemetry import emit_event

logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None


def _get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        # Built from discrete host/port/password, not REDIS_URL -- that var
        # points at the docker-network hostname ("redis"), which doesn't
        # resolve for a process running directly on the host.
        _redis_client = redis.Redis(
            host=REDIS_HOST,
            port=int(REDIS_PORT),
            password=REDIS_PASSWORD,
            db=0,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    return _redis_client


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_and_increment(
    client: redis.Redis,
    key: str,
    max_requests: int,
    window_seconds: int,
) -> Tuple[bool, int]:
    """
    Fixed-window rate check. Returns (allowed, retry_after_seconds).
    retry_after_seconds is 0 when allowed.
    """
    count = client.incr(key)
    if count == 1:
        client.expire(key, window_seconds)

    if count <= max_requests:
        return True, 0

    ttl = client.ttl(key)
    return False, max(ttl, 1)


async def check_ingest_rate_limit(
    request: Request,
    curr_user=Depends(get_current_user_optional),
) -> None:
    identifier = f"user:{curr_user.id}" if curr_user is not None else f"ip:{_get_client_ip(request)}"
    redis_key = f"ratelimit:ingest:{identifier}"

    try:
        client = _get_redis_client()
        allowed, retry_after = check_and_increment(
            client, redis_key, INGEST_RATE_LIMIT_MAX, INGEST_RATE_LIMIT_WINDOW_SECONDS
        )
    except redis.RedisError as e:
        logger.warning(f"Rate limit check failed (Redis unreachable), failing open: {e}")
        emit_event(
            "ratelimit.redis_unavailable",
            {"identifier": identifier, "reason": str(e), "status": "WARNING", "route": "POST /v1/ingest"},
        )
        return

    if not allowed:
        emit_event(
            "ratelimit.exceeded",
            {"identifier": identifier, "retry_after": retry_after, "status": "WARNING", "route": "POST /v1/ingest"},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
