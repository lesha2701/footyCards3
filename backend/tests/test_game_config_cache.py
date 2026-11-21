"""The per-process GameConfig copy (game_config_service): a player's GET may
read a copy a few seconds old; every other request reads the row itself."""
import pytest

from app.models.game_config import GameConfig
from app.services import game_config_service
from app.services.game_config_service import get_config
from tests.conftest import TestSessionLocal


@pytest.fixture
def cache_on(monkeypatch):
    monkeypatch.setattr(game_config_service, "CACHE_SECONDS", 3.0)
    game_config_service._cache.clear()
    token = game_config_service._cache_allowed.set(True)
    yield
    game_config_service._cache_allowed.reset(token)
    game_config_service._cache.clear()


async def _set_slug(slug: str, cups: list) -> None:
    async with TestSessionLocal() as s:
        config = await s.get(GameConfig, 1) or GameConfig(id=1)
        config.free_pack_pack_slug = slug
        config.arena_cup_weekdays = cups
        s.add(config)
        await s.commit()


async def test_a_get_reads_the_copy_until_it_expires(cache_on, monkeypatch):
    await _set_slug("basic", [5, 6])
    async with TestSessionLocal() as s:
        assert (await get_config(s)).free_pack_pack_slug == "basic"
    await _set_slug("premium", [1])

    async with TestSessionLocal() as s:
        config = await get_config(s)
        assert config.free_pack_pack_slug == "basic"  # the copy, seconds old
        # A caller changing a JSON value in place doesn't touch the copy.
        config.arena_cup_weekdays.append(99)
    async with TestSessionLocal() as s:
        assert (await get_config(s)).arena_cup_weekdays == [5, 6]

    # Not a player's GET (a POST, the admin, the bot): the row itself.
    game_config_service._cache_allowed.set(False)
    async with TestSessionLocal() as s:
        assert (await get_config(s)).free_pack_pack_slug == "premium"

    # Expired: a GET reads the row again.
    game_config_service._cache_allowed.set(True)
    for key, (_, template) in list(game_config_service._cache.items()):
        game_config_service._cache[key] = (0.0, template)
    async with TestSessionLocal() as s:
        assert (await get_config(s)).free_pack_pack_slug == "premium"


async def test_the_copy_can_be_changed_and_saved(cache_on):
    await _set_slug("basic", [5, 6])
    async with TestSessionLocal() as s:
        await get_config(s)
    async with TestSessionLocal() as s:
        config = await get_config(s)  # from the copy
        config.free_pack_pack_slug = "elite"
        await s.commit()
    game_config_service._cache_allowed.set(False)
    async with TestSessionLocal() as s:
        config = await get_config(s)
        assert config.free_pack_pack_slug == "elite"
        assert config.arena_cup_weekdays == [5, 6]  # an unchanged column left alone


async def test_only_a_players_get_may_use_the_copy():
    seen = {}

    async def app(scope, receive, send):
        seen[scope["method"], scope["path"]] = game_config_service._cache_allowed.get()

    middleware = game_config_service.ConfigCacheMiddleware(app)
    for method, path in [
        ("GET", "/api/v1/profile/me"), ("POST", "/api/v1/newbie/first-pack"),
        ("GET", "/api/v1/admin/games"), ("GET", "/api/v1/internal/manager/sweep"),
    ]:
        await middleware({"type": "http", "method": method, "path": path}, None, None)
    assert seen == {
        ("GET", "/api/v1/profile/me"): True, ("POST", "/api/v1/newbie/first-pack"): False,
        ("GET", "/api/v1/admin/games"): False, ("GET", "/api/v1/internal/manager/sweep"): False,
    }
