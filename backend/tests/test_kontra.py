from types import SimpleNamespace

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.enums import CardSource, Position, Rarity, TransactionType
from app.models.game_config import GameConfig
from app.models.kontra import KontraBattle, KontraGear
from app.models.transaction import CoinTransaction
from app.services import kontra_service
from app.services.card_creation import create_user_card
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/kontra"
POSITIONS = (Position.ST, Position.RW, Position.CM, Position.CB, Position.GK, Position.LB, Position.CAM)


@pytest.fixture(autouse=True)
async def _setup(request, db_session):
    rate_limit_module._hits.clear()
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    config.kontra_enabled = "disabled" not in request.node.name
    config.kontra_gear_drop_boss_pct = 0
    config.kontra_gear_drop_arena_pct = 0
    for i, pos in enumerate(POSITIONS * 2):  # the pool bots are drawn from
        await create_player(db_session, rating=70 + i % 10, position=pos, display_name=f"Bot pool {i}")
    await db_session.commit()
    yield


async def _set_config(db_session, **values):
    config = await db_session.get(GameConfig, 1)
    for k, v in values.items():
        setattr(config, k, v)
    await db_session.commit()


async def _player(client, db_session, bot_token, telegram_id, rating=84, rarity=Rarity.legendary):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    ids = []
    for i, pos in enumerate(POSITIONS[:5]):
        player = await create_player(db_session, rating=rating - i, position=pos, rarity=rarity,
                                     display_name=f"K{telegram_id}-{i}", club="Реал")
        card = await create_user_card(db_session, user.id, player.id, CardSource.seed)
        ids.append(card.id)
    await db_session.commit()
    return headers, user.id, ids


# ---------------------------------------------------------------------------
# Squad
# ---------------------------------------------------------------------------

async def test_squad_auto_picks_five_with_a_keeper_and_can_be_set(client, db_session, bot_token):
    headers, _, ids = await _player(client, db_session, bot_token, 960001)
    squad = (await client.get(f"{API}/squad", headers=headers)).json()
    assert len(squad["fighters"]) == 5 and any(f["role"] == "goalkeeper" for f in squad["fighters"])
    assert squad["chemistry_pct"] == 10 and "Реал" in squad["chemistry_label"]  # five from one club
    legendary = squad["fighters"][0]
    assert len(legendary["abilities"]) == 3 and legendary["passive"]
    assert squad["leader_id"] == legendary["card"]["card_id"] and squad["leader_aura"]

    bad = await client.put(f"{API}/squad", headers=headers, json={"cards": ids[:2], "leader": 999999})
    assert bad.status_code == 409
    saved = (await client.put(f"{API}/squad", headers=headers, json={"cards": ids[:3], "leader": ids[2]})).json()
    assert [f["card"]["card_id"] for f in saved["fighters"]] == ids[:3] and saved["leader_id"] == ids[2]
    _, _, foreign = await _player(client, db_session, bot_token, 960002)
    assert (await client.put(f"{API}/squad", headers=headers, json={"cards": foreign[:1], "leader": foreign[0]})).status_code == 403


async def test_one_footballer_takes_one_squad_place(client, db_session, bot_token):
    headers, user_id, ids = await _player(client, db_session, bot_token, 960010)
    first = (await client.get(f"{API}/squad", headers=headers)).json()["fighters"][0]["card"]
    # A second copy of the top card and another version of the same footballer.
    copy = await create_user_card(db_session, user_id, (await kontra_service._usable_cards(db_session, user_id))[0].player_id, CardSource.seed)
    other = await create_player(db_session, rating=99, position=Position.ST, display_name=first["display_name"])
    version = await create_user_card(db_session, user_id, other.id, CardSource.seed)
    await db_session.commit()

    squad = (await client.post(f"{API}/squad/auto", headers=headers)).json()
    names = [f["card"]["display_name"] for f in squad["fighters"]]
    assert len(names) == len(set(names)) == 5
    assert first["display_name"] not in [o["card"]["display_name"] for o in squad["options"]]
    for dup in (copy.id, version.id):
        r = await client.put(f"{API}/squad", headers=headers, json={"cards": [ids[0], dup], "leader": ids[0]})
        assert r.status_code == 409


async def test_disabled_flag_blocks_battles(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 960003)
    assert (await client.get(f"{API}/hub", headers=headers)).json()["enabled"] is False
    assert (await client.post(f"{API}/boss/start", headers=headers, json={"manual": False})).status_code == 409


# ---------------------------------------------------------------------------
# Arena
# ---------------------------------------------------------------------------

async def test_arena_auto_battle_moves_rating_and_pays(client, db_session, bot_token):
    headers, uid, _ = await _player(client, db_session, bot_token, 960010, rating=92)
    arena = (await client.get(f"{API}/arena", headers=headers)).json()
    assert len(arena["offers"]) == 3 and all(o["is_bot"] for o in arena["offers"])
    battle = (await client.post(f"{API}/arena/start", headers=headers, json={"offer": 0, "manual": False})).json()
    assert battle["status"] == "finished" and battle["result"] in ("win", "loss") and battle["events"]
    config = await db_session.get(GameConfig, 1)
    expected = config.kontra_rating_win if battle["result"] == "win" else -config.kontra_rating_loss
    assert battle["rating_delta"] == expected
    user = await get_user_by_telegram_id(db_session, 960010)
    assert user.kontra_rating == 1000 + expected and user.kontra_rewarded_attempts_today == 1
    # The offer list was used up and comes back fresh.
    assert len((await client.get(f"{API}/arena", headers=headers)).json()["offers"]) == 3
    txs = (await db_session.execute(select(CoinTransaction).where(
        CoinTransaction.user_id == uid, CoinTransaction.type == TransactionType.kontra_reward,
    ))).scalars().all()
    assert len(txs) == 1 and txs[0].amount == battle["reward_coins"]


async def test_arena_against_another_players_defence(client, db_session, bot_token):
    headers_a, _, _ = await _player(client, db_session, bot_token, 960011, rating=90)
    headers_b, uid_b, ids_b = await _player(client, db_session, bot_token, 960012, rating=80)
    await client.put(f"{API}/squad", headers=headers_b, json={"cards": ids_b, "leader": ids_b[0]})
    arena = (await client.post(f"{API}/arena/refresh", headers=headers_a)).json()
    real = [o for o in arena["offers"] if not o["is_bot"]]
    assert real and real[0]["name"] and len(real[0]["cards"]) == 5
    battle = (await client.post(f"{API}/arena/start", headers=headers_a, json={"offer": real[0]["index"], "manual": False})).json()
    stored = await db_session.get(KontraBattle, battle["id"])
    assert stored.opponent_user_id == uid_b


async def test_manual_battle_waits_validates_and_retries_are_noops(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 960020)
    await client.get(f"{API}/arena", headers=headers)
    battle = (await client.post(f"{API}/arena/start", headers=headers, json={"offer": 1, "manual": True})).json()
    assert battle["status"] == "in_progress" and battle["can_act"] and battle["manual"]
    # One battle at a time.
    blocked = await client.post(f"{API}/boss/start", headers=headers, json={"manual": False})
    assert blocked.status_code == 409 and blocked.json()["error"]["details"]["active_battle_id"] == battle["id"]

    me = next(u for u in battle["units"] if u["id"] == battle["turn_of"])
    other = next(u for u in battle["units"] if u["side"] == "me" and u["id"] != me["id"])
    url = f"{API}/battles/{battle['id']}/act"
    wrong = await client.post(url, headers=headers, json={"version": battle["version"], "unit_id": other["id"], "ability": "strike"})
    assert wrong.status_code == 409
    body = {"version": battle["version"], "unit_id": me["id"], "ability": "strike"}
    after = (await client.post(url, headers=headers, json=body)).json()
    assert after["version"] > battle["version"] and any(e["kind"] == "hit" for e in after["events"])
    again = (await client.post(url, headers=headers, json=body)).json()  # a retried request
    assert again["version"] == after["version"] and again["events"] == []
    stale = await client.post(url, headers=headers, json={**body, "ability": "strike", "unit_id": after["turn_of"] or me["id"]})
    assert stale.status_code == 409

    done = (await client.post(f"{API}/battles/{battle['id']}/auto", headers=headers, json={"version": after["version"]})).json()
    assert done["status"] == "finished" and done["auto"]


async def test_forfeit_is_a_loss_without_reward(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 960021)
    await client.get(f"{API}/arena", headers=headers)
    battle = (await client.post(f"{API}/arena/start", headers=headers, json={"offer": 0, "manual": True})).json()
    end = (await client.post(f"{API}/battles/{battle['id']}/forfeit", headers=headers)).json()
    assert end["result"] == "loss" and end["reward_coins"] == 0 and end["rating_delta"] < 0


async def test_arena_hourly_and_daily_reward_limits(client, db_session, bot_token):
    await _set_config(db_session, hourly_game_limit=2, kontra_daily_limit=1)
    headers, _, _ = await _player(client, db_session, bot_token, 960022)
    await client.get(f"{API}/arena", headers=headers)
    first = (await client.post(f"{API}/arena/start", headers=headers, json={"offer": 0, "manual": False})).json()
    await client.get(f"{API}/arena", headers=headers)
    second = (await client.post(f"{API}/arena/start", headers=headers, json={"offer": 0, "manual": False})).json()
    assert first["reward_coins"] > 0 and second["reward_coins"] == 0  # daily rewarded cap
    await client.get(f"{API}/arena", headers=headers)
    third = await client.post(f"{API}/arena/start", headers=headers, json={"offer": 0, "manual": False})
    assert third.status_code == 409 and "retry_after_seconds" in third.json()["error"]["details"]
    limits = (await client.get("/api/v1/games/limits", headers=headers)).json()
    assert limits["kontra"] == 0


# ---------------------------------------------------------------------------
# Weekly boss
# ---------------------------------------------------------------------------

async def test_boss_attempts_damage_and_reward_tiers(client, db_session, bot_token):
    await _set_config(db_session, kontra_boss_daily_attempts=2, kontra_boss_max_rounds=6,
                      kontra_boss_reward_tiers=[[0, 10], [1, 30], [10_000_000, 999]])
    headers, uid, _ = await _player(client, db_session, bot_token, 960030)
    info = (await client.get(f"{API}/boss", headers=headers)).json()
    assert info["attempts_left"] == 2 and info["name"] and info["phase"] == 1

    battle = (await client.post(f"{API}/boss/start", headers=headers, json={"manual": False})).json()
    assert battle["status"] == "finished" and battle["mode"] == "boss" and battle["damage"] > 0
    assert battle["reward_coins"] == 30 and battle["boss_name"]
    await client.post(f"{API}/boss/start", headers=headers, json={"manual": False})
    assert (await client.post(f"{API}/boss/start", headers=headers, json={"manual": False})).status_code == 409

    info = (await client.get(f"{API}/boss", headers=headers)).json()
    assert info["attempts_left"] == 0 and info["my_damage"] >= battle["damage"] and info["week_damage"] == info["my_damage"]
    assert info["top"][0]["user_id"] == uid


async def test_gear_drops_from_the_boss(client, db_session, bot_token):
    await _set_config(db_session, kontra_gear_drop_boss_pct=100, kontra_boss_max_rounds=3)
    headers, uid, _ = await _player(client, db_session, bot_token, 960031)
    battle = (await client.post(f"{API}/boss/start", headers=headers, json={"manual": False})).json()
    assert battle["gear_drop"] and battle["gear_drop"]["pct"] > 0
    gear = (await db_session.execute(select(KontraGear).where(KontraGear.user_id == uid))).scalars().all()
    assert len(gear) == 1 and gear[0].source == "boss"


# ---------------------------------------------------------------------------
# «Тактические комплекты»
# ---------------------------------------------------------------------------

async def test_chest_equip_and_gear_counts_in_the_squad(client, db_session, bot_token):
    await _set_config(db_session, kontra_chest_coins=100)
    headers, uid, ids = await _player(client, db_session, bot_token, 960040)
    before = (await client.get(f"{API}/squad", headers=headers)).json()
    listing = (await client.post(f"{API}/gear/chest", headers=headers)).json()
    assert len(listing["items"]) == 1 and listing["balance"] == 400
    piece = listing["items"][0]
    equipped = (await client.post(f"{API}/gear/{piece['id']}/equip", headers=headers, json={"card_id": ids[0]})).json()
    assert equipped["items"][0]["card_id"] == ids[0]
    after = (await client.get(f"{API}/squad", headers=headers)).json()
    fighter = next(f for f in after["fighters"] if f["card"]["card_id"] == ids[0])
    assert fighter["gear_count"] == 1 and after["power"] > before["power"]

    # A second piece for the same slot on the same card takes its place.
    other = KontraGear(user_id=uid, slot=piece["slot"], set_code="speed", rarity="legendary", source="admin")
    db_session.add(other)
    await db_session.commit()
    swapped = (await client.post(f"{API}/gear/{other.id}/equip", headers=headers, json={"card_id": ids[0]})).json()
    on_card = [g for g in swapped["items"] if g["card_id"] == ids[0]]
    assert [g["id"] for g in on_card] == [other.id]
    assert (await client.post(f"{API}/gear/{other.id}/equip", headers=headers, json={"card_id": 123456})).status_code == 403


async def test_stars_chest_delivery_is_idempotent(client, db_session, bot_token):
    headers, uid, _ = await _player(client, db_session, bot_token, 960041)
    user = await get_user_by_telegram_id(db_session, 960041)
    invoice = SimpleNamespace(payload_token="kontra-test-token", stars_amount=25)
    await kontra_service.deliver_stars(db_session, user, invoice)
    await kontra_service.deliver_stars(db_session, user, invoice)
    await db_session.commit()
    gear = (await db_session.execute(select(KontraGear).where(KontraGear.user_id == uid))).scalars().all()
    assert len(gear) == 1 and gear[0].source == "stars"
    ok, _ = await kontra_service.validate_stars(db_session, uid, 25)
    assert ok
