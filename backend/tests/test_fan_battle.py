"""«⚔️ Битва фанатов»: sides, point drops, the underdog bonus, daily battles,
milestones, the final, the boss and the admin page."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

import app.core.rate_limit as rate_limit_module
from app.core.timeutil import local_today
from app.models.badge import UserBadge
from app.models.enums import TaskCategory, TaskConditionType, TransactionType
from app.models.fan_battle import FanBattleLedger, FanBattleMember
from app.models.game_config import GameConfig
from app.models.task import TaskDefinition, UserTask
from app.models.user import User
from app.services import fan_battle_service
from app.services.wallet_service import credit_coins, lock_user_for_update
from tests.factories import create_badge, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/fans"


@pytest.fixture(autouse=True)
async def _setup(request, db_session):
    rate_limit_module._hits.clear()
    fan_battle_service.reset_cache()
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    now = datetime.now(timezone.utc)
    config.fan_battle_enabled = "disabled" not in request.node.name
    config.fan_battle_starts_at = now - timedelta(days=2)
    config.fan_battle_ends_at = now + timedelta(days=5)
    config.fan_battle_settings = {}
    config.halloween_enabled = False
    config.kontra_gear_drop_boss_pct = 0
    await db_session.commit()
    yield
    fan_battle_service.reset_cache()


async def _settings(db_session, **values):
    config = await db_session.get(GameConfig, 1)
    config.fan_battle_settings = {**(config.fan_battle_settings or {}), **values}
    await db_session.commit()


async def _window(db_session, starts_at, ends_at):
    config = await db_session.get(GameConfig, 1)
    config.fan_battle_starts_at, config.fan_battle_ends_at = starts_at, ends_at
    await db_session.commit()
    fan_battle_service.reset_cache()


async def _register(client, db_session, bot_token, telegram_id, side=None):
    headers = telegram_headers(telegram_id, bot_token)
    assert (await client.post("/api/v1/auth/session", headers=headers)).status_code == 200
    user = await get_user_by_telegram_id(db_session, telegram_id)
    uid = user.id
    if side:
        assert (await client.post(f"{API}/side/{side}", headers=headers)).status_code == 200
    return headers, uid


async def _give(db_session, uid, amount, kind="admin"):
    user = await lock_user_for_update(db_session, uid)
    got = await fan_battle_service.add_points(db_session, user, amount, kind)
    await db_session.commit()
    return got


async def _points(db_session, uid) -> int:
    db_session.expire_all()
    config = await db_session.get(GameConfig, 1)
    member = await db_session.get(FanBattleMember, (uid, fan_battle_service.event_key(config)))
    return member.points if member else 0


async def _move_to_yesterday(db_session, uid):
    yesterday = (local_today() - timedelta(days=1)).isoformat()
    await db_session.execute(update(FanBattleLedger).where(FanBattleLedger.user_id == uid).values(day=yesterday))
    await db_session.commit()
    fan_battle_service.reset_cache()


async def _balance(db_session, uid) -> int:
    db_session.expire_all()
    return (await db_session.get(User, uid)).balance


# --- Sides -------------------------------------------------------------------------

async def test_side_is_picked_once(client, db_session, bot_token):
    headers, uid = await _register(client, db_session, bot_token, 980001)
    state = (await client.get(API, headers=headers)).json()
    assert state["enabled"] and state["active"] and state["can_join"] and state["my_side"] is None
    assert [s["code"] for s in state["sides"]] == ["fire", "ice"]

    assert (await client.post(f"{API}/side/water", headers=headers)).status_code == 404
    joined = (await client.post(f"{API}/side/fire", headers=headers)).json()
    assert joined["my_side"] == "fire" and joined["sides"][0]["members"] == 1
    assert (await client.post(f"{API}/side/fire", headers=headers)).status_code == 200  # a retry is fine
    switched = await client.post(f"{API}/side/ice", headers=headers)
    assert switched.status_code == 409


async def test_side_can_be_picked_before_the_start(client, db_session, bot_token):
    now = datetime.now(timezone.utc)
    await _window(db_session, now + timedelta(days=2), now + timedelta(days=9))
    headers, uid = await _register(client, db_session, bot_token, 980002, side="ice")
    state = (await client.get(API, headers=headers)).json()
    assert not state["active"] and state["my_side"] == "ice"
    assert await _give(db_session, uid, 10) == 0  # no points before the start


async def test_nothing_when_disabled(client, db_session, bot_token):
    headers, uid = await _register(client, db_session, bot_token, 980003)
    assert (await client.get(API, headers=headers)).json()["enabled"] is False
    assert (await client.post(f"{API}/side/fire", headers=headers)).status_code == 409


# --- Points ------------------------------------------------------------------------

async def test_rewarded_games_bring_points_up_to_the_daily_cap(client, db_session, bot_token):
    await _settings(db_session, points_per_game=4, points_games_daily_cap=10)
    _, uid = await _register(client, db_session, bot_token, 980010, side="fire")
    for _ in range(4):
        locked = await lock_user_for_update(db_session, uid)
        await credit_coins(db_session, locked, 50, TransactionType.game_reward, "game")
        await db_session.commit()
    assert await _points(db_session, uid) == 10  # 4 + 4 + 2 (cap)

    locked = await lock_user_for_update(db_session, uid)
    await credit_coins(db_session, locked, 50, TransactionType.task_reward, "not a game")
    await db_session.commit()
    assert await _points(db_session, uid) == 10


async def test_no_points_without_a_side(client, db_session, bot_token):
    _, uid = await _register(client, db_session, bot_token, 980011)
    locked = await lock_user_for_update(db_session, uid)
    await credit_coins(db_session, locked, 50, TransactionType.game_reward, "game")
    await db_session.commit()
    assert await _give(db_session, uid, 10) == 0
    assert (await db_session.execute(select(FanBattleLedger).where(FanBattleLedger.user_id == uid))).first() is None


async def test_claimed_task_and_chest_bring_points_once(client, db_session, bot_token):
    await _settings(db_session, points_per_task=5, points_per_daily_chest=7)
    for i in range(6):
        db_session.add(TaskDefinition(
            code=f"fb_{i}", name=f"Task {i}", description="", category=TaskCategory.regular,
            condition_type=TaskConditionType.metric_counter, metric="packs_opened", target_value=1, reward_coins=10,
        ))
    await db_session.commit()
    headers, uid = await _register(client, db_session, bot_token, 980012, side="ice")
    task = (await client.get("/api/v1/tasks", headers=headers)).json()["regular"][0]
    row = await db_session.get(UserTask, task["user_task_id"])
    row.progress, row.completed_at = 1, datetime.now(timezone.utc)
    await db_session.commit()
    assert (await client.post(f"/api/v1/tasks/{task['user_task_id']}/claim", headers=headers)).status_code == 200
    assert await _points(db_session, uid) == 5
    assert (await client.post("/api/v1/tasks/chests/daily/0/claim", headers=headers)).status_code == 200
    assert await _points(db_session, uid) == 12
    assert (await client.post("/api/v1/tasks/chests/daily/0/claim", headers=headers)).status_code == 409
    assert await _points(db_session, uid) == 12


async def test_the_smaller_side_gets_the_underdog_bonus(client, db_session, bot_token):
    await _settings(db_session, underdog_bonus_pct=50, underdog_gap_pct=20, underdog_min_members=3)
    for i in range(3):
        await _register(client, db_session, bot_token, 980020 + i, side="fire")
    headers, ice = await _register(client, db_session, bot_token, 980029, side="ice")
    _, fire = await _register(client, db_session, bot_token, 980028, side="fire")
    fan_battle_service.reset_cache()
    assert await _give(db_session, ice, 10) == 15
    assert await _give(db_session, fire, 10) == 10
    sides = {s["code"]: s for s in (await client.get(API, headers=headers)).json()["sides"]}
    assert sides["ice"]["underdog_bonus_pct"] == 50 and sides["fire"]["underdog_bonus_pct"] == 0


# --- Daily battles -----------------------------------------------------------------

async def test_daily_battle_pays_winners_and_losers_once(client, db_session, bot_token):
    await _settings(db_session, daily_min_points=10, daily_win_coins=300, daily_lose_coins=100, milestones=[])
    fire_h, fire = await _register(client, db_session, bot_token, 980030, side="fire")
    ice_h, ice = await _register(client, db_session, bot_token, 980031, side="ice")
    lazy_h, lazy = await _register(client, db_session, bot_token, 980032, side="ice")
    await _give(db_session, fire, 40)
    await _give(db_session, ice, 20)
    await _give(db_session, lazy, 5)  # under the daily minimum
    for uid in (fire, ice, lazy):
        await _move_to_yesterday(db_session, uid)

    state = (await client.get(API, headers=fire_h)).json()
    yesterday = next(d for d in state["days"] if d["finished"] and d["my_points"])
    assert yesterday["winner"] == "fire" and yesterday["reward_coins"] == 300 and state["claimable"] == 1

    before = await _balance(db_session, fire)
    got = (await client.post(f"{API}/claim", headers=fire_h)).json()
    assert got["coins"] == 300 and await _balance(db_session, fire) == before + 300
    assert (await client.post(f"{API}/claim", headers=fire_h)).status_code == 409  # nothing left

    assert (await client.post(f"{API}/claim", headers=ice_h)).json()["coins"] == 100
    assert (await client.post(f"{API}/claim", headers=lazy_h)).status_code == 409
    assert (await client.get(API, headers=fire_h)).json()["claimable"] == 0


async def test_today_is_not_settled_yet(client, db_session, bot_token):
    await _settings(db_session, daily_min_points=1, milestones=[])
    headers, uid = await _register(client, db_session, bot_token, 980033, side="fire")
    await _give(db_session, uid, 30)
    state = (await client.get(API, headers=headers)).json()
    today = state["days"][-1]
    assert not today["finished"] and today["winner"] is None and state["my_today_points"] == 30
    assert (await client.post(f"{API}/claim", headers=headers)).status_code == 409


# --- Milestones --------------------------------------------------------------------

async def test_milestones_pay_coins_and_the_badge(client, db_session, bot_token):
    badge = await create_badge(db_session, name="Фанат 2026", icon="📣")
    badge_id = badge.id
    await _settings(db_session, fan_badge_id=badge_id, milestones=[
        {"points": 20, "kind": "coins", "amount": 500}, {"points": 50, "kind": "badge"},
    ])
    headers, uid = await _register(client, db_session, bot_token, 980040, side="ice")
    await _give(db_session, uid, 25)
    state = (await client.get(API, headers=headers)).json()
    assert [m["reached"] for m in state["milestones"]] == [True, False]
    assert state["milestones"][1]["badge"]["name"] == "Фанат 2026"
    assert (await client.post(f"{API}/claim", headers=headers)).json()["coins"] == 500

    await _give(db_session, uid, 30)
    got = (await client.post(f"{API}/claim", headers=headers)).json()
    assert got["coins"] == 0 and [b["id"] for b in got["badges"]] == [badge_id]
    assert (await db_session.execute(select(UserBadge).where(
        UserBadge.user_id == uid, UserBadge.badge_id == badge_id,
    ))).scalar_one_or_none() is not None
    assert (await client.post(f"{API}/claim", headers=headers)).status_code == 409


# --- The final ---------------------------------------------------------------------

async def test_final_pays_the_winners_more_plus_badge_and_top_bonus(client, db_session, bot_token):
    champion = await create_badge(db_session, name="Чемпион трибун 2026", icon="🏆")
    champion_id = champion.id
    await _settings(db_session, champion_badge_id=champion_id, final_min_points=10, final_win_coins=3000,
                    final_lose_coins=1000, top_n=1, top_bonus_coins=2000, daily_min_points=10_000, milestones=[])
    fire_h, fire = await _register(client, db_session, bot_token, 980050, side="fire")
    fire2_h, fire2 = await _register(client, db_session, bot_token, 980051, side="fire")
    ice_h, ice = await _register(client, db_session, bot_token, 980052, side="ice")
    await _give(db_session, fire, 60)
    await _give(db_session, fire2, 30)
    await _give(db_session, ice, 70)
    now = datetime.now(timezone.utc)
    await _window(db_session, now - timedelta(days=7), now - timedelta(hours=1))

    state = (await client.get(API, headers=fire_h)).json()
    assert state["finished"] and state["final"]["winner"] == "fire" and state["final"]["my_rank"] == 1
    top = (await client.post(f"{API}/claim", headers=fire_h)).json()
    assert top["coins"] == 5000 and [b["id"] for b in top["badges"]] == [champion_id]
    assert (await client.post(f"{API}/claim", headers=fire2_h)).json()["coins"] == 3000
    lost = (await client.post(f"{API}/claim", headers=ice_h)).json()
    assert lost["coins"] == 1000 + 2000 and lost["badges"] == []  # top fan of the losing side
    assert (await client.post(f"{API}/claim", headers=fire_h)).status_code == 409
    assert await _give(db_session, fire, 10) == 0  # no points after the end


async def test_no_claims_after_the_claim_window(client, db_session, bot_token):
    await _settings(db_session, final_min_points=1, claim_days=2, milestones=[])
    headers, uid = await _register(client, db_session, bot_token, 980053, side="ice")
    await _give(db_session, uid, 20)
    now = datetime.now(timezone.utc)
    await _window(db_session, now - timedelta(days=10), now - timedelta(days=3))
    assert (await client.post(f"{API}/claim", headers=headers)).status_code == 409
    assert (await client.get(API, headers=headers)).json()["claimable"] == 0


# --- «Перебежчик» ------------------------------------------------------------------

async def test_turncoat_replaces_the_weekly_boss(client, db_session, bot_token):
    headers, _ = await _register(client, db_session, bot_token, 980060)
    assert (await client.get("/api/v1/kontra/boss", headers=headers)).json()["code"] == "turncoat"


async def test_weekly_boss_stays_when_disabled(client, db_session, bot_token):
    headers, _ = await _register(client, db_session, bot_token, 980061)
    assert (await client.get("/api/v1/kontra/boss", headers=headers)).json()["code"] != "turncoat"


async def test_boss_bonus_multiplies_and_pays_once(client, db_session, bot_token):
    await _settings(db_session, points_per_game=4, boss_multiplier=3)
    _, uid = await _register(client, db_session, bot_token, 980062, side="fire")
    won = {"winner": "time", "boss": {"code": "turncoat"}}
    locked = await lock_user_for_update(db_session, uid)
    assert await fan_battle_service.grant_boss_bonus(db_session, locked, 1, won) == 8
    assert await fan_battle_service.grant_boss_bonus(db_session, locked, 1, won) == 0
    assert await fan_battle_service.grant_boss_bonus(db_session, locked, 2, {"winner": "foe", "boss": {"code": "turncoat"}}) == 0
    assert await fan_battle_service.grant_boss_bonus(db_session, locked, 3, {"winner": "time", "boss": {"code": "wall"}}) == 0
    await db_session.commit()
    assert await _points(db_session, uid) == 8


# --- Admin -------------------------------------------------------------------------

async def test_admin_switch_dates_and_settings(client, db_session, bot_token):
    admin = telegram_headers(999000001, bot_token)
    token = (await client.post("/api/v1/auth/session", headers=admin)).json()["admin_token"]
    auth = {"Authorization": f"Bearer {token}"}
    got = (await client.get("/api/v1/admin/fan-battle", headers=auth)).json()
    assert got["enabled"] is True and got["settings"]["points_per_game"] == 5 and "members" in got["stats"]
    assert (await client.put("/api/v1/admin/fan-battle", headers=auth, json={
        "settings": {"points_per_game": -1}})).status_code == 409
    assert (await client.put("/api/v1/admin/fan-battle", headers=auth, json={
        "settings": {"sides": [{"code": "a", "name": "A"}]}})).status_code == 409
    saved = (await client.put("/api/v1/admin/fan-battle", headers=auth, json={
        "enabled": False, "settings": {"points_per_game": 9, "unknown": 1, "sides": [
            {"code": "spartak", "name": "Спартак", "emoji": "🔴", "color": "#dc2626"},
            {"code": "cska", "name": "ЦСКА", "emoji": "🔵", "color": "#1d4ed8"},
        ]},
    })).json()
    assert saved["enabled"] is False and saved["settings"]["points_per_game"] == 9
    assert "unknown" not in saved["settings"] and saved["settings"]["sides"][0]["code"] == "spartak"
    inverted = await client.put("/api/v1/admin/fan-battle", headers=auth, json={
        "starts_at": "2026-11-21T00:00:00+03:00", "ends_at": "2026-11-07T00:00:00+03:00",
    })
    assert inverted.status_code == 409
