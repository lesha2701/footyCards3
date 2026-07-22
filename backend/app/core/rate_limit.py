import time
from collections import defaultdict, deque

from app.core.exceptions import RateLimitedError

# In-memory sliding-window rate limiter. Adequate for a single backend
# process; swap for a Redis-backed limiter before scaling horizontally.
_hits: dict[str, deque] = defaultdict(deque)


def check_rate_limit(key: str, max_calls: int, window_seconds: int) -> None:
    now = time.monotonic()
    bucket = _hits[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= max_calls:
        raise RateLimitedError(f"Rate limit exceeded for '{key}': max {max_calls} per {window_seconds}s")
    bucket.append(now)


def rate_limit_dependency(action: str, max_calls: int, window_seconds: int):
    from fastapi import Depends

    from app.core.dependencies import get_current_user

    async def dependency(user=Depends(get_current_user)):
        check_rate_limit(f"{action}:{user.id}", max_calls, window_seconds)
        return user

    return dependency
