import asyncio
import logging
import time

from app.core.slow_log import SlowRequestMiddleware, watch_event_loop


async def _call(app, path="/api/v1/x"):
    sent = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        sent.append(message)

    await app({"type": "http", "method": "GET", "path": path}, receive, send)
    return sent


def _app(delay: float):
    async def inner(scope, receive, send):
        await asyncio.sleep(delay)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})
    return inner


async def test_slow_request_is_logged_with_path_and_status(caplog):
    caplog.set_level(logging.WARNING, logger="app.slow")
    sent = await _call(SlowRequestMiddleware(_app(0.05), threshold=0.01), "/api/v1/career")
    assert sent[0]["status"] == 200
    assert "slow request GET /api/v1/career" in caplog.text
    assert "status=200" in caplog.text


async def test_fast_request_is_not_logged(caplog):
    caplog.set_level(logging.WARNING, logger="app.slow")
    await _call(SlowRequestMiddleware(_app(0), threshold=5))
    assert caplog.text == ""


async def test_blocked_event_loop_is_logged(caplog):
    caplog.set_level(logging.WARNING, logger="app.slow")
    watcher = asyncio.create_task(watch_event_loop(tick=0.01, blocked=0.1))
    await asyncio.sleep(0.02)
    time.sleep(0.2)  # a request computing without awaiting
    await asyncio.sleep(0.05)
    watcher.cancel()
    assert "event loop blocked" in caplog.text


def _crunch(seconds: float) -> None:
    """Stands for a request computing without awaiting."""
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        pass


async def test_stall_sampler_names_the_blocking_code(caplog):
    import threading

    from app.core.slow_log import StallSampler

    caplog.set_level(logging.WARNING, logger="app.slow")
    sampler = StallSampler(threading.get_ident(), stuck_after=0.05, poll=0.01).start()
    watcher = asyncio.create_task(watch_event_loop(tick=0.01, blocked=0.1, sampler=sampler))
    await asyncio.sleep(0.03)
    _crunch(0.3)
    await asyncio.sleep(0.03)
    watcher.cancel()
    sampler.stop()
    stuck = [r.getMessage() for r in caplog.records if "event loop stuck at" in r.getMessage()]
    assert len(stuck) == 1  # once per stall
    assert "_crunch" in stuck[0]
