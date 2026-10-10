"""Sliding-window rate limiter.

Two backends behind one async API:
  * in-memory (default) — per process, fine for a single backend instance;
  * Redis — set RATE_LIMIT_REDIS_URL (e.g. redis://redis:6379/0) to share the
    window across several backend replicas. A sorted set per key holds hit
    timestamps; trim + count + add run in one MULTI pipeline.
If Redis is configured but unreachable the request is let through (logged):
an outage of the limiter must not take the whole game down with it.
"""
import logging
import time
import uuid
from collections import defaultdict, deque

from app.config import get_settings
from app.core.exceptions import RateLimitedError

logger = logging.getLogger(__name__)

_hits: dict[str, deque] = defaultdict(deque)
_redis = None


def _redis_client():
    global _redis
    url = get_settings().rate_limit_redis_url
    if not url:
        return None
    if _redis is None:
        import redis.asyncio as redis_asyncio  # imported only when configured

        _redis = redis_asyncio.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)
    return _redis


def _too_many(key: str, max_calls: int, window_seconds: int) -> RateLimitedError:
    return RateLimitedError(f"Rate limit exceeded for '{key}': max {max_calls} per {window_seconds}s")


def _check_memory(key: str, max_calls: int, window_seconds: int) -> None:
    now = time.monotonic()
    bucket = _hits[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= max_calls:
        raise _too_many(key, max_calls, window_seconds)
    bucket.append(now)


async def _check_redis(client, key: str, max_calls: int, window_seconds: int) -> None:
    now = time.time()
    redis_key = f"rl:{key}"
    member = f"{now}:{uuid.uuid4().hex}"
    try:
        # Add first, then count, all in one MULTI — atomic across replicas.
        # A rejected hit removes its own entry so it does not extend the window.
        async with client.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
            pipe.zadd(redis_key, {member: now})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, window_seconds + 1)
            _, _, count, _ = await pipe.execute()
        if count > max_calls:
            await client.zrem(redis_key, member)
            raise _too_many(key, max_calls, window_seconds)
    except RateLimitedError:
        raise
    except Exception:  # noqa: BLE001 - fail open, see module docstring
        logger.warning("Redis rate limiter unavailable; allowing %s", key, exc_info=True)


async def check_rate_limit(key: str, max_calls: int, window_seconds: int) -> None:
    client = _redis_client()
    if client is None:
        _check_memory(key, max_calls, window_seconds)
    else:
        await _check_redis(client, key, max_calls, window_seconds)


def rate_limit_dependency(action: str, max_calls: int, window_seconds: int):
    from fastapi import Depends

    from app.core.dependencies import get_current_user

    async def dependency(user=Depends(get_current_user)):
        await check_rate_limit(f"{action}:{user.id}", max_calls, window_seconds)
        return user

    return dependency
