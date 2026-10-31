"""«🎃 Ночь тыкв»: pumpkin drops, the shop, the doors, the boss, the themed pack."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

import app.core.rate_limit as rate_limit_module
from app.models.badge import UserBadge
from app.models.card import UserCard
from app.models.card_collection import CardCollection
from app.models.enums import CardSource, Position, Rarity, TaskCategory, TaskConditionType, TransactionType
from app.models.game_config import GameConfig
from app.models.halloween import HalloweenLedger, HalloweenWallet
from app.models.task import TaskDefinition, UserTask
from app.services import halloween_service
from app.services.card_creation import create_user_card
from app.services.pack_service import pick_random_player
from app.services.wallet_service import credit_coins, lock_user_for_update
from tests.factories import create_badge, create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/halloween"


@pytest.fixture(autouse=True)
async def _setup(request, db_session):
    rate_limit_module._hits.clear()
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    now = datetime.now(timezone.utc)
    config.halloween_enabled = "disabled" not in request.node.name
    config.halloween_starts_at = now - timedelta(days=1)
    config.halloween_ends_at = now + timedelta(days=3)
    config.halloween_settings = {}
    config.kontra_gear_drop_boss_pct = 0
    await db_session.commit()
    yield


async def _settings(db_session, **values):
    config = await db_session.get(GameConfig, 1)
    config.halloween_settings = {**(config.halloween_settings or {}), **values}
    await db_session.commit()


async def _register(client, db_session, bot_token, telegram_id):
    headers = telegram_headers(telegram_id, bot_token)
    assert (await client.post("/api/v1/auth/session", headers=headers)).status_code == 200
    return headers, await get_user_by_telegram_id(db_session, telegram_id)


async def _give_pumpkins(db_session, user_id, amount):
    user = await lock_user_for_update(db_session, user_id)
    assert await halloween_service.add_pumpkins(db_session, user, amount, "admin") == amount
    await db_session.commit()


async def _pumpkins(db_session, user_id) -> int:
    db_session.expire_all()
    config = await db_session.get(GameConfig, 1)
    await db_session.refresh(config)
    wallet = await db_session.get(HalloweenWallet, (user_id, halloween_service.event_key(config)))
    return wallet.pumpkins if wallet else 0


# --- Drops -------------------------------------------------------------------------

async def test_rewarded_games_drop_pumpkins_up_to_the_daily_cap(client, db_session, bot_token):
    await _settings(db_session, pumpkins_per_game=4, pumpkins_games_daily_cap=10)
    _, user = await _register(client, db_session, bot_token, 970001)
    uid = user.id
    for _ in range(4):
        locked = await lock_user_for_update(db_session, uid)
        await credit_coins(db_session, locked, 50, TransactionType.game_reward, "game")
        await db_session.commit()
    assert await _pumpkins(db_session, uid) == 10  # 4 + 4 + 2 (cap), then nothing

    # Not a game (a task reward) and no coins → no game pumpkins.
    locked = await lock_user_for_update(db_session, uid)
    await credit_coins(db_session, locked, 50, TransactionType.task_reward, "task")
    await db_session.commit()
    assert await _pumpkins(db_session, uid) == 10


async def test_no_pumpkins_when_the_event_is_disabled(client, db_session, bot_token):
    _, user = await _register(client, db_session, bot_token, 970002)
    uid = user.id
    locked = await lock_user_for_update(db_session, uid)
    await credit_coins(db_session, locked, 50, TransactionType.game_reward, "game")
    await db_session.commit()
    assert await _pumpkins(db_session, uid) == 0
    state = (await client.get(API, headers=telegram_headers(970002, bot_token))).json()
    assert state["enabled"] is False and state["active"] is False


async def test_no_pumpkins_outside_the_dates(client, db_session, bot_token):
    config = await db_session.get(GameConfig, 1)
    config.halloween_ends_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.commit()
    headers, user = await _register(client, db_session, bot_token, 970003)
    uid = user.id
    locked = await lock_user_for_update(db_session, uid)
    await credit_coins(db_session, locked, 50, TransactionType.game_reward, "game")
    await db_session.commit()
    assert await _pumpkins(db_session, uid) == 0
    assert (await client.post(f"{API}/doors/0", headers=headers)).status_code == 409


async def test_claimed_task_and_activity_chest_drop_pumpkins_once(client, db_session, bot_token):
    await _settings(db_session, pumpkins_per_task=5, pumpkins_per_daily_chest=7)
    for i in range(6):
        db_session.add(TaskDefinition(
            code=f"hw_{i}", name=f"Task {i}", description="", category=TaskCategory.regular,
            condition_type=TaskConditionType.metric_counter, metric="packs_opened", target_value=1, reward_coins=10,
        ))
    await db_session.commit()
    headers, user = await _register(client, db_session, bot_token, 970004)
    uid = user.id
    task = (await client.get("/api/v1/tasks", headers=headers)).json()["regular"][0]
    row = await db_session.get(UserTask, task["user_task_id"])
    row.progress, row.completed_at = 1, datetime.now(timezone.utc)
    await db_session.commit()
    assert (await client.post(f"/api/v1/tasks/{task['user_task_id']}/claim", headers=headers)).status_code == 200
    assert await _pumpkins(db_session, uid) == 5
    assert (await client.post("/api/v1/tasks/chests/daily/0/claim", headers=headers)).status_code == 200
    assert await _pumpkins(db_session, uid) == 12
    assert (await client.post("/api/v1/tasks/chests/daily/0/claim", headers=headers)).status_code == 409
    assert await _pumpkins(db_session, uid) == 12


# --- «Лавка тыкв» ----------------------------------------------------------------

async def test_shop_spends_pumpkins_for_coins_and_is_idempotent(client, db_session, bot_token):
    headers, user = await _register(client, db_session, bot_token, 970010)
    uid = user.id
    await _give_pumpkins(db_session, uid, 60)
    balance = user.balance
    first = await client.post(f"{API}/shop/coins", headers=headers, json={"idempotency_key": "buy-coins-0001"})
    assert first.status_code == 200, first.text
    assert first.json()["coins"] == 400 and first.json()["pumpkins"] == 35
    retry = await client.post(f"{API}/shop/coins", headers=headers, json={"idempotency_key": "buy-coins-0001"})
    assert retry.status_code == 200 and retry.json()["pumpkins"] == 35
    await db_session.refresh(user)
    assert user.balance == balance + 400  # paid once
    assert await _pumpkins(db_session, uid) == 35


async def test_shop_refuses_without_enough_pumpkins_and_over_the_limit(client, db_session, bot_token):
    await _settings(db_session, shop=[{"code": "coins", "kind": "coins", "title": "Монеты", "price": 10, "amount": 5,
                                       "limit": 1}])
    headers, user = await _register(client, db_session, bot_token, 970011)
    uid = user.id
    poor = await client.post(f"{API}/shop/coins", headers=headers, json={"idempotency_key": "poor-000001"})
    assert poor.status_code == 409 and poor.json()["error"]["details"]["reason"] == "not_enough_pumpkins"
    await _give_pumpkins(db_session, uid, 50)
    assert (await client.post(f"{API}/shop/coins", headers=headers, json={"idempotency_key": "k-000001"})).status_code == 200
    over = await client.post(f"{API}/shop/coins", headers=headers, json={"idempotency_key": "k-000002"})
    assert over.status_code == 409
    assert await _pumpkins(db_session, uid) == 40
    shop = (await client.get(API, headers=headers)).json()["shop"]
    assert shop[0]["bought"] == 1 and shop[0]["available"] is False


async def test_shop_badge_is_granted_once(client, db_session, bot_token):
    badge = await create_badge(db_session, name="Тыква 2026", icon="🎃")
    await _settings(db_session, badge_id=badge.id)
    headers, user = await _register(client, db_session, bot_token, 970012)
    uid = user.id
    await _give_pumpkins(db_session, uid, 400)
    ok = await client.post(f"{API}/shop/badge_2026", headers=headers, json={"idempotency_key": "badge-00001"})
    assert ok.status_code == 200 and ok.json()["badge"]["name"] == "Тыква 2026"
    again = await client.post(f"{API}/shop/badge_2026", headers=headers, json={"idempotency_key": "badge-00002"})
    assert again.status_code == 409
    owned = (await db_session.execute(select(func.count(UserBadge.id)).where(UserBadge.user_id == uid))).scalar_one()
    assert owned == 1


async def test_shop_pack_drops_only_the_collection(client, db_session, bot_token):
    collection = CardCollection(name="Ночь живых Легенд", description="", card_skin="zombie")
    db_session.add(collection)
    await db_session.commit()
    legend = await create_player(db_session, rarity=Rarity.legendary, display_name="Зомби-Легенда",
                                 collection_id=collection.id, is_pack_droppable=False)
    await create_player(db_session, rarity=Rarity.rare, display_name="Обычный")
    pack = await create_pack(db_session, "hw-pack", 100, 2, {Rarity.rare: 1.0}, player_pool=f"collection:{collection.id}")
    await _settings(db_session, pack_id=pack.id, collection_id=collection.id)
    headers, user = await _register(client, db_session, bot_token, 970013)
    uid = user.id
    await _give_pumpkins(db_session, uid, 200)
    bought = await client.post(f"{API}/shop/legends_pack", headers=headers, json={"idempotency_key": "pack-000001"})
    assert bought.status_code == 200, bought.text
    cards = bought.json()["cards"]
    assert len(cards) == 2 and all(c["player"]["id"] == legend.id for c in cards)
    assert cards[0]["player"]["collection_skin"] == "zombie"
    # The regular pool never drops the non-droppable collection card.
    assert (await pick_random_player(db_session, Rarity.legendary)).id != legend.id
    state = (await client.get(API, headers=headers)).json()
    assert state["collection"]["owned"] == 1 and state["collection"]["total"] == 1


async def test_shop_closed_after_the_event(client, db_session, bot_token):
    headers, user = await _register(client, db_session, bot_token, 970014)
    uid = user.id
    await _give_pumpkins(db_session, uid, 100)
    config = await db_session.get(GameConfig, 1)
    config.halloween_ends_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()
    assert (await client.post(f"{API}/shop/coins", headers=headers, json={"idempotency_key": "late-00001"})).status_code == 409


# --- «Кошелёк или жизнь» --------------------------------------------------------

async def test_door_opens_once_a_day_and_pays_a_treat(client, db_session, bot_token):
    await _settings(db_session, door_trick_pct=0, door_treats=[{"weight": 1, "kind": "coins", "amount": 77}])
    headers, user = await _register(client, db_session, bot_token, 970020)
    uid = user.id
    balance = user.balance
    door = await client.post(f"{API}/doors/1", headers=headers)
    assert door.status_code == 200, door.text
    assert door.json()["outcome"] == "treat" and door.json()["amount"] == 77
    await db_session.refresh(user)
    assert user.balance == balance + 77
    assert (await client.post(f"{API}/doors/2", headers=headers)).status_code == 409
    assert (await client.post(f"{API}/doors/5", headers=headers)).status_code == 404
    state = (await client.get(API, headers=headers)).json()
    assert state["door_today"]["amount"] == 77


async def test_door_trick_puts_a_zombie_frame_on_one_card(client, db_session, bot_token):
    await _settings(db_session, door_trick_pct=100, door_zombie_weight=1, door_joke_weight=0)
    headers, user = await _register(client, db_session, bot_token, 970021)
    uid = user.id
    player = await create_player(db_session, rarity=Rarity.rare, display_name="Жертва")
    await create_user_card(db_session, uid, player.id, CardSource.seed)
    await db_session.commit()
    balance = user.balance
    door = (await client.post(f"{API}/doors/0", headers=headers)).json()
    assert door["outcome"] == "trick" and door["kind"] == "zombie_frame" and door["zombie_player_name"] == "Жертва"
    state = (await client.get(API, headers=headers)).json()
    assert state["zombie_player_id"] == player.id and state["zombie_until"]
    await db_session.refresh(user)
    assert user.balance == balance  # harmless
    assert (await db_session.execute(select(func.count(UserCard.id)).where(UserCard.owner_id == uid))).scalar_one() == 1


async def test_door_pumpkin_treat(client, db_session, bot_token):
    await _settings(db_session, door_trick_pct=0, door_treats=[{"weight": 1, "kind": "pumpkins", "amount": 9}])
    headers, user = await _register(client, db_session, bot_token, 970022)
    uid = user.id
    assert (await client.post(f"{API}/doors/2", headers=headers)).json()["kind"] == "pumpkins"
    assert await _pumpkins(db_session, uid) == 9


# --- «Безголовый вратарь» -------------------------------------------------------

async def test_headless_keeper_replaces_the_boss_and_doubles_pumpkins(client, db_session, bot_token):
    await _settings(db_session, pumpkins_per_game=3, boss_multiplier=2)
    config = await db_session.get(GameConfig, 1)
    config.kontra_boss_max_rounds = 2
    config.kontra_boss_reward_tiers = [[0, 10]]
    await db_session.commit()
    headers, user = await _register(client, db_session, bot_token, 970030)
    uid = user.id
    for i, pos in enumerate((Position.ST, Position.CM, Position.CB, Position.GK, Position.RW)):
        p = await create_player(db_session, rating=90 - i, position=pos, rarity=Rarity.legendary, display_name=f"H{i}")
        await create_user_card(db_session, uid, p.id, CardSource.seed)
    await db_session.commit()
    info = (await client.get("/api/v1/kontra/boss", headers=headers)).json()
    assert info["code"] == "headless" and info["name"] == "Безголовый вратарь"
    battle = (await client.post("/api/v1/kontra/boss/start", headers=headers, json={"manual": False})).json()
    assert battle["status"] == "finished" and battle["boss_name"] == "Безголовый вратарь"
    pumpkins = await _pumpkins(db_session, uid)
    bonus = (await db_session.execute(select(HalloweenLedger).where(
        HalloweenLedger.user_id == uid, HalloweenLedger.kind == "boss",
    ))).scalar_one_or_none()
    assert pumpkins == (6 if bonus is not None else 3)  # ×2 only for standing until the whistle


async def test_boss_bonus_doubles_and_pays_once(client, db_session, bot_token):
    await _settings(db_session, pumpkins_per_game=3, boss_multiplier=2)
    _, user = await _register(client, db_session, bot_token, 970032)
    uid = user.id
    won = {"winner": "time", "boss": {"code": "headless"}}
    locked = await lock_user_for_update(db_session, uid)
    assert await halloween_service.grant_boss_bonus(db_session, locked, 1, won) == 3
    assert await halloween_service.grant_boss_bonus(db_session, locked, 1, won) == 0  # same battle
    assert await halloween_service.grant_boss_bonus(db_session, locked, 2, {"winner": "foe", "boss": {"code": "headless"}}) == 0
    assert await halloween_service.grant_boss_bonus(db_session, locked, 3, {"winner": "time", "boss": {"code": "wall"}}) == 0
    await db_session.commit()
    assert await _pumpkins(db_session, uid) == 3


async def test_boss_won_rule():
    assert halloween_service.boss_won({"winner": "time"}) and halloween_service.boss_won({"winner": "me"})
    assert not halloween_service.boss_won({"winner": "foe"})
    assert not halloween_service.boss_won({"winner": "time", "forfeit": True})


async def test_weekly_boss_stays_when_disabled(client, db_session, bot_token):
    headers, _ = await _register(client, db_session, bot_token, 970031)
    assert (await client.get("/api/v1/kontra/boss", headers=headers)).json()["code"] != "headless"


# --- Admin -----------------------------------------------------------------------

async def test_admin_switch_dates_and_settings(client, db_session, bot_token):
    admin = telegram_headers(999000001, bot_token)
    token = (await client.post("/api/v1/auth/session", headers=admin)).json()["admin_token"]
    auth = {"Authorization": f"Bearer {token}"}
    got = (await client.get("/api/v1/admin/halloween", headers=auth)).json()
    assert got["enabled"] is True and got["settings"]["pumpkins_per_game"] == 3
    bad = await client.put("/api/v1/admin/halloween", headers=auth, json={"settings": {"pumpkins_per_game": -1}})
    assert bad.status_code == 409
    saved = (await client.put("/api/v1/admin/halloween", headers=auth, json={
        "enabled": False, "settings": {"pumpkins_per_game": 9, "unknown": 1},
    })).json()
    assert saved["enabled"] is False and saved["settings"]["pumpkins_per_game"] == 9 and "unknown" not in saved["settings"]
    inverted = await client.put("/api/v1/admin/halloween", headers=auth, json={
        "starts_at": "2026-11-05T00:00:00+03:00", "ends_at": "2026-10-31T00:00:00+03:00",
    })
    assert inverted.status_code == 409
