from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.timeutil import ensure_aware
from app.models.card import UserCard
from app.models.enums import CardSource, GameSessionStatus, GameType, Position, Rarity
from app.models.game import GameSession
from app.models.newbie import NewbieProgress
from app.services import starter_offer_service
from app.services.game_config_service import get_config
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/newbie"


async def _setup(db_session, *, newbie=True):
    for rarity in (Rarity.rare, Rarity.epic, Rarity.legendary):
        for position in (Position.GK, Position.LB, Position.CB, Position.RB, Position.CDM, Position.CM,
                         Position.CAM, Position.LW, Position.ST, Position.RW):
            await create_player(db_session, rarity=rarity, position=position)
            if position == Position.CB:
                await create_player(db_session, rarity=rarity, position=position)
    await create_pack(db_session, "basic", price=100, card_count=1, probabilities={Rarity.rare: 1.0})
    config = await get_config(db_session)
    config.newbie_since = datetime.now(timezone.utc) - timedelta(hours=1) if newbie else None
    await db_session.commit()


async def _register(client, db_session, bot_token, telegram_id):
    headers = telegram_headers(telegram_id, bot_token)
    assert (await client.post("/api/v1/auth/session", headers=headers)).status_code == 200
    return headers, await get_user_by_telegram_id(db_session, telegram_id)


async def test_old_players_are_not_newbies(client, db_session, bot_token):
    await _setup(db_session, newbie=False)
    headers, _ = await _register(client, db_session, bot_token, 860001)
    assert (await client.get(API, headers=headers)).json()["active"] is False
    assert (await client.post(f"{API}/first-pack", headers=headers)).status_code == 403


async def test_first_pack_has_an_epic_bound_and_replays(client, db_session, bot_token):
    await _setup(db_session)
    headers, user = await _register(client, db_session, bot_token, 860002)

    state = (await client.get(API, headers=headers)).json()
    assert state["active"] is True and state["first_pack_done"] is False

    # The team pack waits for the first one.
    assert (await client.post(f"{API}/squad-pack", headers=headers)).status_code == 409

    resp = await client.post(f"{API}/first-pack", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["pack"]["name"] == "Пак дебютанта"
    assert sorted(c["card"]["player"]["rarity"] for c in body["cards"]) == ["epic", "rare", "rare"]
    assert all(c["card"]["is_user_locked"] and c["card"]["bound_until"] for c in body["cards"])

    again = (await client.post(f"{API}/first-pack", headers=headers)).json()
    assert again["opening_id"] == body["opening_id"]
    cards = (await db_session.execute(select(UserCard).where(UserCard.owner_id == user.id))).scalars().all()
    assert len(cards) == 3 and all(c.source == CardSource.newbie for c in cards)

    # Bound: the «замок» can't come off.
    resp = await client.patch(
        "/api/v1/collection/cards/lock", headers=headers, json={"card_ids": [cards[0].id], "locked": False},
    )
    assert resp.status_code == 409


async def test_squad_pack_fills_every_arena_position(client, db_session, bot_token):
    await _setup(db_session)
    headers, _ = await _register(client, db_session, bot_token, 860003)
    await client.post(f"{API}/first-pack", headers=headers)
    resp = await client.post(f"{API}/squad-pack", headers=headers)
    assert resp.status_code == 200
    cards = resp.json()["cards"]
    assert len(cards) == 11
    assert len({c["card"]["player"]["id"] for c in cards}) == 11
    positions = sorted(c["card"]["player"]["position"] for c in cards)
    assert positions == sorted(["GK", "LB", "CB", "CB", "RB", "CDM", "CM", "CAM", "LW", "ST", "RW"])
    assert (await client.get(API, headers=headers)).json()["squad_pack_done"] is True


async def test_task_pays_once_after_playing(client, db_session, bot_token):
    await _setup(db_session)
    headers, user = await _register(client, db_session, bot_token, 860004)
    assert (await client.post(f"{API}/claim/task:penalty", headers=headers)).status_code == 409

    db_session.add(GameSession(user_id=user.id, game_type=GameType.penalty, status=GameSessionStatus.won))
    await db_session.commit()
    state = (await client.get(API, headers=headers)).json()
    task = next(t for t in state["tasks"] if t["code"] == "penalty")
    assert task["played"] is True and task["claimed"] is False

    balance = user.balance
    resp = await client.post(f"{API}/claim/task:penalty", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["rewards"]["coins"] == 1000
    assert resp.json()["rewards"]["new_balance"] == balance + 1000
    assert (await client.post(f"{API}/claim/task:penalty", headers=headers)).status_code == 409


async def test_day_gifts_open_on_their_days(client, db_session, bot_token):
    await _setup(db_session)
    headers, user = await _register(client, db_session, bot_token, 860005)
    await client.get(API, headers=headers)
    assert (await client.post(f"{API}/claim/day2", headers=headers)).status_code == 409
    assert (await client.post(f"{API}/arena-card", headers=headers)).status_code == 409

    progress = await db_session.get(NewbieProgress, user.id)
    progress.start_day = progress.start_day - timedelta(days=2)
    await db_session.commit()

    resp = await client.post(f"{API}/claim/day2", headers=headers)
    assert resp.status_code == 200 and resp.json()["rewards"]["coins"] == 10000
    resp = await client.post(f"{API}/claim/day3", headers=headers)
    assert resp.status_code == 200
    card = resp.json()["rewards"]["cards"][0]
    assert card["player"]["rarity"] == "legendary" and card["bound_until"]


async def test_starter_offer_waits_for_day_two(client, db_session, bot_token):
    await _setup(db_session)
    _, user = await _register(client, db_session, bot_token, 860006)
    config = await get_config(db_session)
    start = starter_offer_service.starts_at(user, config)
    assert start > datetime.now(timezone.utc)
    assert start - ensure_aware(user.created_at) <= timedelta(days=1)


async def test_first_arena_opponent_is_a_weak_bot(client, db_session, bot_token):
    from app.services import newbie_service

    await _setup(db_session)
    _, user = await _register(client, db_session, bot_token, 860007)
    config = await get_config(db_session)
    pending = await newbie_service.first_arena_opponent(db_session, user, config)
    assert pending["user_id"] is None and pending["bot_ratio"] < 0.7

    config.newbie_since = None
    assert await newbie_service.first_arena_opponent(db_session, user, config) is None


async def test_finale_after_every_step(client, db_session, bot_token):
    await _setup(db_session)
    config = await get_config(db_session)
    config.newbie_tasks = [config.newbie_tasks[0]]
    await db_session.commit()
    headers, user = await _register(client, db_session, bot_token, 860008)
    await client.get(API, headers=headers)
    assert (await client.post(f"{API}/claim/finale", headers=headers)).status_code == 409

    progress = await db_session.get(NewbieProgress, user.id)
    progress.claimed = {k: {"at": "x", "ref": None} for k in ("first_pack", "squad_pack", "arena", "task:penalty", "day2", "day3")}
    await db_session.commit()
    state = (await client.get(API, headers=headers)).json()
    assert state["active"] is True and state["finale_ready"] is True and state["finale"]["coins"] == 5000

    resp = await client.post(f"{API}/claim/finale", headers=headers)
    assert resp.status_code == 200 and resp.json()["rewards"]["coins"] == 5000
    assert resp.json()["state"]["active"] is False
