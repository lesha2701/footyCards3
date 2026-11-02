"""«💯 Нам 100 дней!»: the gift calendar, the community goal «Сотня», the
personal recap «Мои 100 дней» and its share, the admin page."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.core.timeutil import local_today
from app.models.anniversary import AnniversaryMember
from app.models.badge import UserBadge
from app.models.enums import CardSource, GameSessionStatus, GameType, Rarity, TransactionType
from app.models.game import GameSession
from app.models.game_config import GameConfig
from app.models.user import User
from app.services import anniversary_service
from app.services.card_creation import create_user_card
from app.services.wallet_service import credit_coins, lock_user_for_update
from tests.factories import create_badge, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/anniversary"


@pytest.fixture(autouse=True)
async def _setup(request, db_session):
    rate_limit_module._hits.clear()
    anniversary_service.reset_cache()
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    now = datetime.now(timezone.utc)
    config.anniversary_enabled = "disabled" not in request.node.name
    config.anniversary_starts_at = now - timedelta(days=1)
    config.anniversary_ends_at = now + timedelta(days=5)
    config.anniversary_settings = {}
    config.halloween_enabled = False
    config.fan_battle_enabled = False
    await db_session.commit()
    yield
    anniversary_service.reset_cache()


async def _settings(db_session, **values):
    config = await db_session.get(GameConfig, 1)
    config.anniversary_settings = {**(config.anniversary_settings or {}), **values}
    await db_session.commit()
    anniversary_service.reset_cache()


async def _register(client, db_session, bot_token, telegram_id):
    headers = telegram_headers(telegram_id, bot_token)
    assert (await client.post("/api/v1/auth/session", headers=headers)).status_code == 200
    user = await get_user_by_telegram_id(db_session, telegram_id)
    return headers, user.id


async def _play(db_session, uid, n):
    for _ in range(n):
        locked = await lock_user_for_update(db_session, uid)
        await credit_coins(db_session, locked, 20, TransactionType.game_reward, "game")
        await db_session.commit()
    anniversary_service.reset_cache()


async def _balance(db_session, uid) -> int:
    db_session.expire_all()
    return (await db_session.get(User, uid)).balance


async def _to_tomorrow(db_session, uid):
    """Pretend the last gift was taken yesterday."""
    db_session.expire_all()
    config = await db_session.get(GameConfig, 1)
    member = await db_session.get(AnniversaryMember, (uid, anniversary_service.event_key(config)))
    member.calendar_last_day = (local_today() - timedelta(days=1)).isoformat()
    await db_session.commit()


# --- Calendar ----------------------------------------------------------------------

async def test_calendar_gives_one_gift_a_day_in_order(client, db_session, bot_token):
    badge = await create_badge(db_session, name="100 дней", icon="💯")
    badge_id = badge.id
    await _settings(db_session, badge_id=badge_id, calendar=[{"coins": 300}, {"coins": 500, "badge": True}])
    headers, uid = await _register(client, db_session, bot_token, 990001)
    state = (await client.get(API, headers=headers)).json()
    assert state["calendar_ready"] and [d["status"] for d in state["calendar"]] == ["today", "locked"]
    assert state["calendar"][1]["reward"]["badge"]["name"] == "100 дней"

    before = await _balance(db_session, uid)
    first = (await client.post(f"{API}/calendar/claim", headers=headers)).json()
    assert first["rewards"]["coins"] == 300 and await _balance(db_session, uid) == before + 300
    again = await client.post(f"{API}/calendar/claim", headers=headers)
    assert again.status_code == 409  # once a day
    assert not (await client.get(API, headers=headers)).json()["calendar_ready"]

    await _to_tomorrow(db_session, uid)
    second = (await client.post(f"{API}/calendar/claim", headers=headers)).json()
    assert second["rewards"]["coins"] == 500 and second["rewards"]["badge"]["id"] == badge_id
    assert (await db_session.execute(select(UserBadge).where(
        UserBadge.user_id == uid, UserBadge.badge_id == badge_id,
    ))).scalar_one_or_none() is not None

    await _to_tomorrow(db_session, uid)
    assert (await client.post(f"{API}/calendar/claim", headers=headers)).status_code == 409  # all taken


async def test_calendar_closed_when_disabled(client, db_session, bot_token):
    headers, _ = await _register(client, db_session, bot_token, 990002)
    assert (await client.get(API, headers=headers)).json()["enabled"] is False
    assert (await client.post(f"{API}/calendar/claim", headers=headers)).status_code == 409


# --- «Сотня» -----------------------------------------------------------------------

async def test_rewarded_games_fill_the_community_goal(client, db_session, bot_token):
    await _settings(db_session, community_goal=10, community_min_games=2, community_tiers=[
        {"pct": 50, "coins": 400}, {"pct": 100, "coins": 1000},
    ])
    a_headers, a = await _register(client, db_session, bot_token, 990010)
    b_headers, b = await _register(client, db_session, bot_token, 990011)
    lazy_headers, lazy = await _register(client, db_session, bot_token, 990012)
    await _play(db_session, a, 4)
    await _play(db_session, lazy, 1)

    locked = await lock_user_for_update(db_session, b)
    await credit_coins(db_session, locked, 20, TransactionType.task_reward, "not a game")
    await db_session.commit()

    state = (await client.get(API, headers=a_headers)).json()
    assert state["community"]["total"] == 5 and state["community"]["my_games"] == 4
    assert [t["reached"] for t in state["community"]["tiers"]] == [True, False] and state["community"]["claimable"]

    got = (await client.post(f"{API}/community/claim", headers=a_headers)).json()
    assert got["rewards"]["coins"] == 400
    assert (await client.post(f"{API}/community/claim", headers=a_headers)).status_code == 409
    assert (await client.post(f"{API}/community/claim", headers=lazy_headers)).status_code == 409  # 1 game < 2

    await _play(db_session, b, 5)
    assert (await client.post(f"{API}/community/claim", headers=b_headers)).json()["rewards"]["coins"] == 1400
    assert (await client.post(f"{API}/community/claim", headers=a_headers)).json()["rewards"]["coins"] == 1000


async def test_no_games_counted_outside_the_dates(client, db_session, bot_token):
    _, uid = await _register(client, db_session, bot_token, 990013)
    config = await db_session.get(GameConfig, 1)
    config.anniversary_starts_at = datetime.now(timezone.utc) + timedelta(days=1)
    await db_session.commit()
    await _play(db_session, uid, 3)
    config = await db_session.get(GameConfig, 1)
    assert await anniversary_service.community_total(db_session, anniversary_service.event_key(config), fresh=True) == 0


# --- «Мои 100 дней» ----------------------------------------------------------------

async def test_recap_counts_the_players_own_history(client, db_session, bot_token):
    headers, uid = await _register(client, db_session, bot_token, 990020)
    star = await create_player(db_session, rating=93, rarity=Rarity.legendary, display_name="Звезда")
    other = await create_player(db_session, rating=70, display_name="Простой")
    for p in (star, other, other):
        await create_user_card(db_session, uid, p.id, CardSource.seed)
    for _ in range(3):
        db_session.add(GameSession(user_id=uid, game_type=GameType.penalty, status=GameSessionStatus.rewarded))
    db_session.add(GameSession(user_id=uid, game_type=GameType.memory_sequence, status=GameSessionStatus.rewarded))
    await db_session.commit()

    recap = (await client.get(f"{API}/recap", headers=headers)).json()
    assert recap["cards"] == 3 and recap["unique_players"] == 2
    assert recap["best_card_name"] == "Звезда" and recap["best_card_rating"] == 93
    assert recap["favourite_mode"] == "Пенальти" and recap["favourite_mode_games"] == 3 and recap["games"] == 4
    assert recap["days_with_us"] >= 1 and recap["player_number"] >= 1

    shared = (await client.post("/api/v1/share/prepare", headers=headers, json={"kind": "anniversary_recap", "id": 0})).json()
    assert "Мои первые" in shared["caption"] and "Звезда (93)" in shared["caption"]
    assert shared["share_url"].startswith("https://t.me/share/url")


async def test_recap_gift_is_paid_once(client, db_session, bot_token):
    await _settings(db_session, recap_coins=150)
    headers, uid = await _register(client, db_session, bot_token, 990021)
    before = await _balance(db_session, uid)
    assert (await client.post(f"{API}/recap/claim", headers=headers)).json()["rewards"]["coins"] == 150
    assert await _balance(db_session, uid) == before + 150
    assert (await client.post(f"{API}/recap/claim", headers=headers)).status_code == 409
    assert (await client.get(API, headers=headers)).json()["recap_claimed"] is True


# --- Admin -------------------------------------------------------------------------

async def test_admin_switch_dates_and_settings(client, db_session, bot_token):
    admin = telegram_headers(999000001, bot_token)
    token = (await client.post("/api/v1/auth/session", headers=admin)).json()["admin_token"]
    auth = {"Authorization": f"Bearer {token}"}
    got = (await client.get("/api/v1/admin/anniversary", headers=auth)).json()
    assert got["enabled"] is True and got["settings"]["community_goal"] == 50000 and "members" in got["stats"]
    for bad in ({"community_goal": -1}, {"calendar": []}, {"calendar": [{"card_rarity": "mythic"}]},
                {"community_tiers": [{"pct": 150, "coins": 1}]}):
        assert (await client.put("/api/v1/admin/anniversary", headers=auth, json={"settings": bad})).status_code == 409
    saved = (await client.put("/api/v1/admin/anniversary", headers=auth, json={
        "enabled": False, "settings": {"community_goal": 1000, "unknown": 1},
    })).json()
    assert saved["enabled"] is False and saved["settings"]["community_goal"] == 1000 and "unknown" not in saved["settings"]
    inverted = await client.put("/api/v1/admin/anniversary", headers=auth, json={
        "starts_at": "2026-12-01T00:00:00+03:00", "ends_at": "2026-11-21T00:00:00+03:00",
    })
    assert inverted.status_code == 409
