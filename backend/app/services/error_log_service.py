"""Unhandled exceptions (the 500s) go to the log and to `server_errors`, so
the bot can tell the admins (bot/services/watchdog.py: a daily digest) —
otherwise a broken screen is only noticed when players complain.

Recording is best-effort: its own session (the request's may be broken by
the very error), and a failure to record never changes the response.
"""
import logging
import re
import traceback as tb

from fastapi import Request

from app.database import AsyncSessionLocal
from app.models.server_error import ServerError

logger = logging.getLogger("app.errors")

# Overridden in tests (the app's engine isn't the test database).
session_factory = AsyncSessionLocal

# Numbers in paths become «{id}», so one bug on many objects is one line.
_ID = re.compile(r"/\d+(?=/|$)")


def path_pattern(path: str) -> str:
    return _ID.sub("/{id}", path)[:255]


async def record(request: Request, exc: Exception) -> None:
    logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    try:
        async with session_factory() as session:
            session.add(ServerError(
                method=request.method[:8], path=path_pattern(request.url.path),
                error=f"{type(exc).__name__}: {exc}"[:255],
                traceback="".join(tb.format_exception(exc))[-8000:],
            ))
            await session.commit()
    except Exception:  # noqa: BLE001 - recording must never break the error response
        logger.warning("Could not record a server error", exc_info=True)
