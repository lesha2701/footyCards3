"""Finding what freezes the API in production.

The backend runs as one uvicorn process: a request that computes for a
second without awaiting stalls every other player's request (the Mini App
sits on its black loading screen meanwhile). Two cheap signals in the logs:

- SlowRequestMiddleware — "slow request POST /api/v1/... 3.2s" for any
  request slower than SLOW_REQUEST_S (waiting on the DB or on a stalled loop);
- watch_event_loop — "event loop blocked 1.4s" when the loop itself did not
  run for that long, i.e. some request computed synchronously. The slow
  requests logged around that moment name the culprit;
- StallSampler — a thread that, while the loop is stuck, logs once where:
  "event loop stuck at app/services/x.py:120 fn <- …" (our frames, then
  the innermost library frame), so the blocking code is named exactly.
"""
import asyncio
import logging
import sys
import threading
import time
import traceback

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


class StallSampler:
    """The loop beats (`beat()` from watch_event_loop); a daemon thread checks
    the beat and, once per stall, logs the loop thread's stack."""

    def __init__(self, loop_thread_id: int, stuck_after: float = LOOP_TICK_S + LOOP_BLOCKED_S, poll: float = 0.1):
        self.loop_thread_id = loop_thread_id
        self.stuck_after = stuck_after
        self.poll = poll
        self.last_beat = time.monotonic()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="stall-sampler", daemon=True)

    def beat(self) -> None:
        self.last_beat = time.monotonic()

    def start(self) -> "StallSampler":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        reported = None
        while not self._stop.wait(self.poll):
            beat = self.last_beat
            if beat == reported or time.monotonic() - beat < self.stuck_after:
                continue
            frame = sys._current_frames().get(self.loop_thread_id)
            if frame is not None:
                logger.warning("event loop stuck at %s", where(frame))
            reported = beat


def where(frame) -> str:
    """Our own frames (innermost first) and the innermost frame overall."""
    stack = traceback.extract_stack(frame)
    ours = [f for f in stack if "/app/" in f.filename.replace("\\", "/") and "site-packages" not in f.filename]
    parts = [f"{_short(f.filename)}:{f.lineno} {f.name}" for f in reversed(ours[-6:])]
    inner = stack[-1]
    if not ours or inner is not ours[-1]:
        parts.append(f"[in {_short(inner.filename)}:{inner.lineno} {inner.name}]")
    return " <- ".join(parts) or "?"


def _short(filename: str) -> str:
    filename = filename.replace("\\", "/")
    for marker in ("/site-packages/", "/app/app/", "/app/"):
        if marker in filename:
            return filename.split(marker, 1)[1]
    return filename


async def watch_event_loop(
    tick: float = LOOP_TICK_S, blocked: float = LOOP_BLOCKED_S, sampler: "StallSampler | None" = None,
) -> None:
    """Sleeps `tick` in a loop; waking up much later means the loop was busy."""
    while True:
        started = time.perf_counter()
        if sampler is not None:
            sampler.beat()
        await asyncio.sleep(tick)
        lag = time.perf_counter() - started - tick
        if lag >= blocked:
            logger.warning("event loop blocked %.1fs", lag)
