"""The single GameConfig row (id=1).

It is huge — ~900 columns, ~100 of them JSON — and almost every request
reads it: loading and decoding it cost ~8 ms of CPU each time, about a third
of what a home-screen request costs. So a player's GET request (the home
screen, lists, statuses) gets it from a per-process copy at most
CACHE_SECONDS old. Everything else — POST/PUT/… (rewards, limits, any game
action), the admin panel and the bot's /internal calls — still reads the row
itself (`ConfigCacheMiddleware` decides), so an admin save or a direct
`UPDATE game_config` is seen by those at once and by GETs within seconds.
"""
import asyncio
import contextvars
import time
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import make_transient_to_detached
from sqlalchemy.orm.attributes import set_committed_value

from app.models.game_config import GameConfig

CACHE_SECONDS = 3.0
_cache_allowed: contextvars.ContextVar[bool] = contextvars.ContextVar("game_config_cache_allowed", default=False)
# (loop, database) -> (expires at, detached template)
_cache: dict[str, tuple[float, GameConfig]] = {}

_COLUMNS: list[str] = []
_MUTABLE: list[str] = []


def _columns() -> tuple[list[str], list[str]]:
    if not _COLUMNS:
        for attr in inspect(GameConfig).column_attrs:
            _COLUMNS.append(attr.key)
            if "JSON" in type(attr.columns[0].type).__name__.upper():
                _MUTABLE.append(attr.key)
    return _COLUMNS, _MUTABLE


def _copy(value: Any) -> Any:
    # JSON values only: dicts, lists and scalars.
    if type(value) is dict:
        return {k: _copy(v) for k, v in value.items()}
    if type(value) is list:
        return [_copy(v) for v in value]
    return value


class ConfigCacheMiddleware:
    """Pure ASGI: lets get_config use the cached copy for a player's GET."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            allowed = scope.get("method") == "GET" and not path.startswith(("/api/v1/admin", "/api/v1/internal"))
            token = _cache_allowed.set(allowed)
            try:
                await self.app(scope, receive, send)
            finally:
                _cache_allowed.reset(token)
            return
        await self.app(scope, receive, send)


def _cache_key(db: AsyncSession) -> str | None:
    bind = db.bind
    if not isinstance(bind, AsyncEngine):
        return None
    return f"{id(asyncio.get_running_loop())}:{bind.url.render_as_string(hide_password=False)}"


def _template(config: GameConfig) -> GameConfig:
    """A detached copy of the loaded row, to merge into later sessions."""
    columns, mutable = _columns()
    copy = GameConfig._sa_class_manager.new_instance()  # bare ORM state, no defaults
    state = config.__dict__
    for key in columns:
        if key in state:
            set_committed_value(copy, key, _copy(state[key]) if key in mutable else state[key])
    make_transient_to_detached(copy)
    return copy


async def get_config(db: AsyncSession) -> GameConfig:
    present = db.sync_session.identity_map.get(db.sync_session.identity_key(GameConfig, 1))
    if present is not None:
        # Already in this session: db.get returns it (reloading it if a
        # commit/rollback expired it) — never merge the copy over it.
        return await db.get(GameConfig, 1)
    key = _cache_key(db) if CACHE_SECONDS > 0 and _cache_allowed.get() else None
    if key is not None:
        hit = _cache.get(key)
        if hit is not None and hit[0] > time.monotonic():
            config = await db.merge(hit[1], load=False)
            # Its own JSON values: a caller changing one in place must not
            # change the copy every later request gets.
            for name in _columns()[1]:
                value = config.__dict__.get(name)
                if type(value) in (dict, list):
                    set_committed_value(config, name, _copy(value))
            return config

    config = await db.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db.add(config)
        await db.commit()
        await db.refresh(config)
    if key is not None:
        _cache[key] = (time.monotonic() + CACHE_SECONDS, _template(config))
    return config
