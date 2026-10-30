"""Finding what freezes the API in production.

The backend runs as one uvicorn process: a request that computes for a
second without awaiting stalls every other player's request (the Mini App
sits on its black loading screen meanwhile). Two cheap signals in the logs:

- SlowRequestMiddleware — "slow request POST /api/v1/... 3.2s" for any
  request slower than SLOW_REQUEST_S (waiting on the DB or on a stalled loop);
- watch_event_loop — "event loop blocked 1.4s" when the loop itself did not
  run for that long, i.e. some request computed synchronously. The slow
  requests logged around that moment name the culprit.
"""
import asyncio
import logging
import time

logger = logging.getLogger("app.slow")

SLOW_REQUEST_S = 2.0
LOOP_TICK_S = 0.25
LOOP_BLOCKED_S = 0.5


class SlowRequestMiddleware:
    """Pure ASGI (not BaseHTTPMiddleware): no extra task per request."""

    def __init__(self, app, threshold: float = SLOW_REQUEST_S):
        self.app = app
        self.threshold = threshold

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = {"code": 0}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - started
            if elapsed >= self.threshold:
                logger.warning(
                    "slow request %s %s %.1fs status=%s",
                    scope.get("method"), scope.get("path"), elapsed, status["code"],
                )


async def watch_event_loop(tick: float = LOOP_TICK_S, blocked: float = LOOP_BLOCKED_S) -> None:
    """Sleeps `tick` in a loop; waking up much later means the loop was busy."""
    while True:
        started = time.perf_counter()
        await asyncio.sleep(tick)
        lag = time.perf_counter() - started - tick
        if lag >= blocked:
            logger.warning("event loop blocked %.1fs", lag)
