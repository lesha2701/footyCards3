import asyncio
import time


class RateLimiter:
    """Token bucket: at most `rate` acquisitions per second, sustained."""

    def __init__(self, rate: float) -> None:
        self._rate = rate
        self._tokens = rate
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self._rate, self._tokens + (now - self._updated) * self._rate)
                self._updated = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await asyncio.sleep((1 - self._tokens) / self._rate)
