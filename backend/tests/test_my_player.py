"""«Мой игрок»: constructor, XP from rewarded actions (daily cap), levels and
attribute points, rating cap/tiers, and taking part in «Карьера тренера»."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.career import CareerParticipant
from app.models.lifestyle import LifestyleItem
from app.models.enums import TransactionType
from app.models.card_skill import UserSkillToken
from app.models.my_player import MyPlayer
from app.models.user import User
from app.services import career_service, my_player_service, wallet_service
from app.services.game_config_service import get_config
from tests.factories import get_user_by_telegram_id
from tests.test_career import _player_with_cards
from tests.utils import telegram_headers

API = "/api/v1"
LOOK = {"skin": 2, "hair": 12, "hair_color": 1, "beard": 1, "eye_color": 3, "kit": 4, "kit_pattern": 1}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _login(client, db_session, bot_token, tg_id):
    await client.post(f"{API}/auth/session", headers=telegram_headers(tg_id, bot_token))
    user = await get_user_by_telegram_id(db_session, tg_id)
    return user.id, telegram_headers(tg_id, bot_token)


async def _create(client, headers, **overrides):
    body = {"name": "Виктор Ж.", "number": 9, "position": "ST", "appearance": LOOK, **overrides}
    return await client.post(f"{API}/my-player", headers=headers, json=body)


async def test_create_validates_and_starts_bronze(client, db_session, bot_token):
    _, headers = await _login(client, db_session, bot_token, 870001)
    view = (await client.get(f"{API}/my-player", headers=headers)).json()
    assert view["player"] is None and view["level"] == 1 and view["points_available"] == 0

    assert (await _create(client, headers, name="x")).status_code == 409
    assert (await _create(client, headers, name="Хуйкин")).status_code == 409
    assert (await _create(client, headers, position="ZZ")).status_code == 409
    assert (await _create(client, headers, number=100)).status_code == 409
    assert (await _create(client, headers, appearance={**LOOK, "hair": 99})).status_code == 409
    assert (await _create(client, headers, appearance={**LOOK, "eye_color": 6})).status_code == 409

    resp = await _create(client, headers)
    assert resp.status_code == 200, resp.text
    player = resp.json()["player"]
    assert player["name"] == "Виктор Ж." and player["position"] == "ST" and player["category"] == "FWD"
    assert set(player["attributes"]) == {"atk", "def"} and player["key_attr"] == "atk"
    assert player["attributes"]["atk"] > player["attributes"]["def"]
    assert player["attack_rating"] == player["attributes"]["atk"]
    assert 50 <= player["rating"] < 60 and player["tier"] == "bronze"
    assert player["appearance"] == LOOK
    # Only one per user.
    assert (await _create(client, headers)).status_code == 409


async def test_position_change_only_within_line(client, db_session, bot_token):
    _, headers = await _login(client, db_session, bot_token, 870002)
    await _create(client, headers)
    assert (await client.patch(f"{API}/my-player", headers=headers, json={"position": "CB"})).status_code == 409
    resp = await client.patch(f"{API}/my-player", headers=headers, json={"position": "LW", "name": "Новое Имя", "number": 7})
    assert resp.status_code == 200
    assert resp.json()["player"]["position"] == "LW" and resp.json()["player"]["number"] == 7


async def test_reward_xp_daily_cap_levels_and_training(client, db_session, bot_token):
    user_id, headers = await _login(client, db_session, bot_token, 870003)
    config = await get_config(db_session)
    config.my_player_xp_per_reward = 60
    config.my_player_xp_daily_cap = 150
    await db_session.commit()
    await _create(client, headers)

    user = await wallet_service.lock_user_for_update(db_session, user_id)
    for _ in range(4):
        await wallet_service.credit_coins(db_session, user, 10, TransactionType.game_reward, "test")
    # Spending/stakes/zero rewards give nothing.
    await wallet_service.credit_coins(db_session, user, 10, TransactionType.trade_coins_received, "test")
    await wallet_service.credit_coins(db_session, user, 0, TransactionType.game_reward, "test")
    await db_session.commit()
    assert user.my_player_xp == 150  # 60 + 60 + 30 (cap), then nothing

    view = (await client.get(f"{API}/my-player", headers=headers)).json()
    assert view["xp_today"] == 150 and view["level"] == 2 and view["xp_into_level"] == 50
    assert view["points_available"] == config.my_player_points_per_level

    before = view["player"]["attributes"]["def"]
    resp = await client.post(f"{API}/my-player/train", headers=headers, json={"attr": "def", "points": 2})
    assert resp.status_code == 200, resp.text
    assert resp.json()["player"]["attributes"]["def"] == before + 2
    assert resp.json()["player"]["defense_rating"] == before + 2
    assert resp.json()["points_available"] == config.my_player_points_per_level - 2
    too_many = await client.post(f"{API}/my-player/train", headers=headers, json={"attr": "def", "points": 5})
    assert too_many.status_code == 409
    assert (await client.post(f"{API}/my-player/train", headers=headers, json={"attr": "xyz"})).status_code == 409

    # Next day the cap resets.
    user = await wallet_service.lock_user_for_update(db_session, user_id)
    user.my_player_xp_day = user.my_player_xp_day - timedelta(days=1)
    await wallet_service.credit_coins(db_session, user, 10, TransactionType.daily_reward, "test")
    await db_session.commit()
    assert user.my_player_xp == 210


async def test_rating_cap_and_tiers(db_session):
    config = await get_config(db_session)
    mp = MyPlayer(user_id=1, name="Тест", number=1, position=my_player_service.Position.ST, appearance={},
                  attributes={"atk": 99, "def": 99}, points_spent=0)
    assert my_player_service.rating_of(mp, config) == config.my_player_rating_cap
    assert my_player_service.tier_of(config.my_player_rating_cap, config) == "legend"
    assert my_player_service.tier_of(70, config) == "silver"
    assert my_player_service.tier_of(50, config) == "bronze"
    legacy = MyPlayer(user_id=2, name="Старый", number=1, position=my_player_service.Position.CB, appearance={},
                      attributes={"pac": 50, "sho": 45, "pas": 45, "dfn": 60, "phy": 55}, points_spent=6)
    assert my_player_service.migrate_legacy(legacy) and legacy.points_spent == 0
    assert legacy.attributes["def"] > legacy.attributes["atk"]
    level, into, need = my_player_service.level_info(0, config)
    assert (level, into) == (1, 0) and need == config.my_player_xp_level_base


async def test_my_player_plays_in_career_and_earns_xp(client, db_session, bot_token):
    user_id, headers = await _player_with_cards(client, db_session, bot_token, 870004)
    assert (await _create(client, headers)).status_code == 200
    season = (await client.post(f"{API}/career/seasons", headers=headers, json={"difficulty": "amateur"})).json()["season"]
    mine_id = my_player_service.card_id_for(user_id)
    entry = next(s for s in season["squad"] if s["card_id"] == mine_id)
    assert entry["card"] is None and entry["my_player"]["name"] == "Виктор Ж."

    # Put «Мой игрок» up front; a lineup with him is accepted.
    st_slot = next(s["code"] for s in season["slots"] if s["category"] == "FWD")
    lineup = {code: cid for code, cid in season["lineup"].items() if cid != mine_id}
    lineup[st_slot] = mine_id
    resp = await client.put(f"{API}/career/lineup", headers=headers, json={"slots": lineup})
    assert resp.status_code == 200, resp.text
    assert resp.json()["season"]["lineup"][st_slot] == mine_id

    xp_before = (await db_session.get(User, user_id)).my_player_xp
    later = datetime.now(timezone.utc) + timedelta(days=8)
    assert await career_service.resolve_due(db_session, season["id"], now=later) == 14
    db_session.expire_all()
    part = (await db_session.execute(
        select(CareerParticipant).where(CareerParticipant.season_id == season["id"])
    )).scalar_one()
    assert str(mine_id) in part.condition  # fatigue/cards tracked like any squad card
    assert (await db_session.get(User, user_id)).my_player_xp > xp_before


async def test_public_view(client, db_session, bot_token):
    owner_id, owner_headers = await _login(client, db_session, bot_token, 870005)
    _, other_headers = await _login(client, db_session, bot_token, 870006)
    assert (await client.get(f"{API}/my-player/users/{owner_id}", headers=other_headers)).json()["player"] is None
    await _create(client, owner_headers)
    body = (await client.get(f"{API}/my-player/users/{owner_id}", headers=other_headers)).json()
    assert body["player"]["name"] == "Виктор Ж." and body["level"] == 1


# --- stage 2: skill, training, cosmetics, leaderboard ---------------------------

async def test_skill_assign_upgrade_replace_like_a_card(client, db_session, bot_token):
    user_id, headers = await _login(client, db_session, bot_token, 870010)
    await _create(client, headers)  # ST
    config = await get_config(db_session)
    view = (await client.get(f"{API}/my-player", headers=headers)).json()
    options = {o["code"] for o in view["skill"]["options"]}
    assert "sniper" in options and "interceptor" not in options  # interceptor is not for strikers
    assert view["skill"]["level"] == 0
    assert view["skill"]["assign_token_cost"] == config.card_skill_assign_token_cost

    need = config.card_skill_assign_token_cost + config.card_skill_upgrade_2_token_cost + config.card_skill_upgrade_3_token_cost
    coins = config.card_skill_assign_coin_cost + config.card_skill_upgrade_2_coin_cost + config.card_skill_upgrade_3_coin_cost
    user = await db_session.get(User, user_id)
    user.balance = coins
    if config.card_skill_assign_token_cost:
        # No tokens yet: assigning is refused, exactly like for a card.
        assert (await client.put(f"{API}/my-player/skill", headers=headers, json={"code": "sniper"})).status_code == 409
    token_row = UserSkillToken(user_id=user_id, skill_code="sniper", quantity=need)
    db_session.add(token_row)
    await db_session.commit()

    assert (await client.put(f"{API}/my-player/skill", headers=headers, json={"code": "interceptor"})).status_code == 409
    resp = await client.put(f"{API}/my-player/skill", headers=headers, json={"code": "sniper"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["skill"]["level"] == 1
    card = await my_player_service.engine_card(db_session, user_id, config)
    assert card.skill_code == "sniper" and card.skill_level == 1

    for level in (2, 3):
        resp = await client.post(f"{API}/my-player/skill/upgrade", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["skill"]["level"] == level
    assert (await client.post(f"{API}/my-player/skill/upgrade", headers=headers)).status_code == 409  # max
    token_id = token_row.id
    db_session.expire_all()
    assert (await db_session.get(UserSkillToken, token_id)).quantity == 0
    assert (await db_session.get(User, user_id)).balance == 0

    # Replacing: card «replace» price in tokens of the new skill, starts at I.
    config = await get_config(db_session)
    user = await db_session.get(User, user_id)
    user.balance = config.card_skill_replace_coin_cost
    await db_session.commit()
    replace_tokens = config.card_skill_replace_token_cost
    await db_session.commit()
    if replace_tokens:
        assert (await client.put(f"{API}/my-player/skill", headers=headers, json={"code": "dribbler"})).status_code == 409
    db_session.add(UserSkillToken(user_id=user_id, skill_code="dribbler", quantity=replace_tokens))
    await db_session.commit()
    resp = await client.put(f"{API}/my-player/skill", headers=headers, json={"code": "dribbler"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["skill"]["code"] == "dribbler" and resp.json()["skill"]["level"] == 1


async def test_daily_training_once_a_day_with_timing_checks(client, db_session, bot_token):
    user_id, headers = await _login(client, db_session, bot_token, 870011)
    await _create(client, headers)
    config = await get_config(db_session)
    user = await db_session.get(User, user_id)

    # Finishing without starting / too fast is refused.
    assert (await client.post(f"{API}/my-player/training/finish", headers=headers, json={"hits": 3})).status_code == 409
    assert (await client.post(f"{API}/my-player/training/start", headers=headers)).status_code == 200
    assert (await client.post(f"{API}/my-player/training/finish", headers=headers, json={"hits": 3})).status_code == 409

    start = datetime.now(timezone.utc)
    await my_player_service.training_start(db_session, user, now=start)
    view = await my_player_service.training_finish(db_session, user, 2, now=start + timedelta(seconds=10))
    expected = config.my_player_training_xp_base + 2 * config.my_player_training_xp_per_hit
    assert view["training_xp"] == expected and view["training"]["done_today"]
    db_session.expire_all()
    assert (await db_session.get(User, user_id)).my_player_xp == expected  # on top of the daily cap counter
    assert (await client.post(f"{API}/my-player/training/start", headers=headers)).status_code == 409


async def test_cosmetics_buy_debits_and_equip(client, db_session, bot_token):
    user_id, headers = await _login(client, db_session, bot_token, 870012)
    await _create(client, headers)
    config = await get_config(db_session)
    price = config.my_player_cosmetic_prices["headband"]
    user = await db_session.get(User, user_id)
    user.balance = price + 5
    await db_session.commit()

    assert (await client.put(f"{API}/my-player/cosmetics/equip", headers=headers,
                             json={"kind": "accessory", "code": "headband"})).status_code == 409
    resp = await client.post(f"{API}/my-player/cosmetics/buy", headers=headers, json={"code": "headband"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["player"]["accessory"] == "headband"
    db_session.expire_all()
    assert (await db_session.get(User, user_id)).balance == 5
    # Twice / not for sale / not enough coins.
    assert (await client.post(f"{API}/my-player/cosmetics/buy", headers=headers, json={"code": "headband"})).status_code == 409
    assert (await client.post(f"{API}/my-player/cosmetics/buy", headers=headers, json={"code": "crown"})).status_code == 409
    assert (await client.post(f"{API}/my-player/cosmetics/buy", headers=headers, json={"code": "bg_gold"})).status_code != 200

    resp = await client.put(f"{API}/my-player/cosmetics/equip", headers=headers, json={"kind": "accessory", "code": None})
    assert resp.status_code == 200 and resp.json()["player"]["accessory"] is None
    assert "headband" in resp.json()["cosmetics"]["owned"]


async def test_leaderboard_all_and_friends(client, db_session, bot_token):
    a_id, a_headers = await _login(client, db_session, bot_token, 870013)
    b_id, b_headers = await _login(client, db_session, bot_token, 870014)
    await _create(client, a_headers)
    await _create(client, b_headers, name="Второй Игрок")
    mp_b = await my_player_service.get_my_player(db_session, b_id)
    mp_b.points_spent = 10
    mp_b.attributes = {"atk": 78, "def": 46}
    await db_session.commit()

    board = (await client.get(f"{API}/my-player/leaderboard", headers=a_headers)).json()
    ranks = {e["user_id"]: e["rank"] for e in board["entries"]}
    assert ranks[b_id] < ranks[a_id]
    friends = (await client.get(f"{API}/my-player/leaderboard?scope=friends", headers=a_headers)).json()
    assert [e["user_id"] for e in friends["entries"]] == [a_id]  # not friends yet


# --- extra trainings, Stars purchases, «Имущество» -------------------------------

async def test_extra_trainings_for_coins_with_daily_max(client, db_session, bot_token):
    user_id, headers = await _login(client, db_session, bot_token, 870020)
    await _create(client, headers)
    config = await get_config(db_session)
    config.my_player_extra_trainings_max = 2
    user = await db_session.get(User, user_id)
    user.balance = config.my_player_extra_training_coins * 5
    await db_session.commit()

    # Free run first.
    now = datetime.now(timezone.utc)
    await my_player_service.training_start(db_session, user, now=now)
    await my_player_service.training_finish(db_session, user, 1, now=now + timedelta(seconds=6))
    assert (await client.post(f"{API}/my-player/training/start", headers=headers)).status_code == 409

    for _ in range(2):
        assert (await client.post(f"{API}/my-player/extra-training/buy", headers=headers)).status_code == 200
    third = await client.post(f"{API}/my-player/extra-training/buy", headers=headers)
    assert third.status_code == 409  # daily max
    view = (await client.get(f"{API}/my-player", headers=headers)).json()
    assert view["training"]["extra_credits"] == 2 and view["training"]["can_train"]
    assert view["training"]["extra_left_today"] == 0

    db_session.expire_all()
    user = await db_session.get(User, user_id)
    xp_before = user.my_player_xp
    await my_player_service.training_start(db_session, user, now=now)
    view = await my_player_service.training_finish(db_session, user, 3, now=now + timedelta(seconds=6))
    assert view["training"]["extra_credits"] == 1
    db_session.expire_all()
    assert (await db_session.get(User, user_id)).my_player_xp == xp_before + view["training_xp"]


async def test_stars_extra_training_and_item_delivery(client, db_session, bot_token, monkeypatch):
    from app.services import stars_payment_service
    from tests.test_gifts import INTERNAL_HEADERS, _deliver, _fake_invoice_link

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    user_id, headers = await _login(client, db_session, bot_token, 870021)
    await _create(client, headers)
    config = await get_config(db_session)

    resp = await client.post(f"{API}/my-player/stars-invoice", headers=headers, json={"purchase": "training"})
    assert resp.status_code == 200, resp.text
    token, stars = resp.json()["payload_token"], resp.json()["stars_amount"]
    assert stars == config.my_player_extra_training_stars
    pre = await client.post("/api/v1/internal/stars-payments/pre-checkout", headers=INTERNAL_HEADERS,
                            json={"payload_token": token, "total_amount": stars})
    assert pre.json()["ok"] is True
    delivered = await _deliver(client, token, 870021, "charge-mp-1", stars)
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["my_player_result"]["kind"] == "training"
    # Redelivery is idempotent.
    assert (await _deliver(client, token, 870021, "charge-mp-1", stars)).status_code == 200
    view = (await client.get(f"{API}/my-player", headers=headers)).json()
    assert view["training"]["extra_credits"] == 1

    item = LifestyleItem(name="Вилла", category="estate", emoji="🏝️", coins_price=0, stars_price=50, prestige=100, max_supply=1)
    db_session.add(item)
    await db_session.commit()
    assert (await client.post(f"/api/v1/lifestyle/{item.id}/buy", headers=headers)).status_code == 409  # stars only
    resp = await client.post(f"{API}/my-player/stars-invoice", headers=headers, json={"purchase": "item", "item_id": item.id})
    token = resp.json()["payload_token"]
    assert (await _deliver(client, token, 870021, "charge-mp-2", 50)).status_code == 200
    catalog = (await client.get("/api/v1/lifestyle", headers=headers)).json()
    villa = next(i for i in catalog["items"] if i["id"] == item.id)
    assert villa["owned"] and villa["serial_number"] == 1 and villa["sold_out"]
    assert catalog["prestige"] == 100
    # Sold out / already owned: a new invoice is refused.
    again = await client.post(f"{API}/my-player/stars-invoice", headers=headers, json={"purchase": "item", "item_id": item.id})
    assert again.status_code == 409


async def test_lifestyle_coins_purchase_and_public(client, db_session, bot_token):
    user_id, headers = await _login(client, db_session, bot_token, 870022)
    _, other = await _login(client, db_session, bot_token, 870023)
    item = LifestyleItem(name="Хэтчбек", category="car", emoji="🚗", coins_price=1500, stars_price=0, prestige=10)
    off = LifestyleItem(name="Старый", category="car", emoji="🚙", coins_price=10, stars_price=0, prestige=1, is_active=False)
    db_session.add_all([item, off])
    user = await db_session.get(User, user_id)
    user.balance = 2000
    await db_session.commit()

    catalog = (await client.get("/api/v1/lifestyle", headers=headers)).json()
    assert [i["name"] for i in catalog["items"]] == ["Хэтчбек"]  # inactive hidden
    resp = await client.post(f"/api/v1/lifestyle/{item.id}/buy", headers=headers)
    assert resp.status_code == 200, resp.text
    assert (await client.post(f"/api/v1/lifestyle/{item.id}/buy", headers=headers)).status_code == 409
    assert (await client.post(f"/api/v1/lifestyle/{off.id}/buy", headers=headers)).status_code == 409
    db_session.expire_all()
    assert (await db_session.get(User, user_id)).balance == 500
    public = (await client.get(f"/api/v1/lifestyle/users/{user_id}", headers=other)).json()
    assert [i["name"] for i in public["items"]] == ["Хэтчбек"] and public["prestige"] == 10


async def test_admin_lifestyle_crud(client, db_session, bot_token):
    from tests.test_gifts import _admin_auth

    auth = await _admin_auth(client, bot_token)
    bad = await client.post("/api/v1/admin/lifestyle", headers=auth, json={"name": "Без цены", "category": "car"})
    assert bad.status_code == 409
    resp = await client.post("/api/v1/admin/lifestyle", headers=auth, json={
        "name": "Яхта", "category": "other", "emoji": "🛥️", "stars_price": 300, "prestige": 150, "max_supply": 10,
    })
    assert resp.status_code == 200, resp.text
    item_id = resp.json()["id"]
    upd = await client.put(f"/api/v1/admin/lifestyle/{item_id}", headers=auth, json={"coins_price": 9000, "is_active": False})
    assert upd.status_code == 200 and upd.json()["coins_price"] == 9000 and not upd.json()["is_active"]
    assert len((await client.get("/api/v1/admin/lifestyle", headers=auth)).json()) == 1
    assert (await client.delete(f"/api/v1/admin/lifestyle/{item_id}", headers=auth)).status_code == 204


async def test_premium_hairstyle_for_stars_sets_appearance_and_status(client, db_session, bot_token, monkeypatch):
    from app.services import stars_payment_service
    from tests.test_gifts import INTERNAL_HEADERS, _deliver, _fake_invoice_link

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    _, headers = await _login(client, db_session, bot_token, 870090)
    await _create(client, headers)
    view = (await client.get(f"{API}/my-player", headers=headers)).json()
    neymar = next(c for c in view["cosmetics"]["catalog"] if c["code"] == "hair_neymar")
    assert neymar["kind"] == "hair" and neymar["stars_price"] == 120 and neymar["price"] == 0
    assert neymar["status"] == 30 and neymar["hair_index"] == 14
    assert (await client.post(f"{API}/my-player/cosmetics/buy", headers=headers, json={"code": "hair_neymar"})).status_code == 409

    resp = await client.post(f"{API}/my-player/stars-invoice", headers=headers, json={"purchase": "cosmetic", "code": "hair_neymar"})
    token, stars = resp.json()["payload_token"], resp.json()["stars_amount"]
    assert (await _deliver(client, token, 870090, "charge-hair", stars)).status_code == 200
    view = (await client.get(f"{API}/my-player", headers=headers)).json()
    assert view["player"]["appearance"]["hair"] == 14 and view["cosmetics"]["hair"] == "hair_neymar"
    assert (await client.get(f"{API}/lifestyle", headers=headers)).json()["prestige"] == 30

    # Editing the look keeps the premium style; picking a free hairstyle takes it off.
    same = await client.patch(f"{API}/my-player", headers=headers, json={"appearance": {**LOOK, "hair": 14}})
    assert same.status_code == 200 and same.json()["player"]["appearance"]["hair"] == 14
    free = await client.patch(f"{API}/my-player", headers=headers, json={"appearance": {**LOOK, "hair": 3}})
    assert free.json()["player"]["appearance"]["hair"] == 3 and free.json()["cosmetics"]["hair"] is None
    # Put it back on, then off again → back to the free hairstyle.
    on = await client.put(f"{API}/my-player/cosmetics/equip", headers=headers, json={"kind": "hair", "code": "hair_neymar"})
    assert on.json()["player"]["appearance"]["hair"] == 14
    off = await client.put(f"{API}/my-player/cosmetics/equip", headers=headers, json={"kind": "hair", "code": None})
    assert off.json()["player"]["appearance"]["hair"] == 3
    # Status stays while owned, worn or not.
    assert (await client.get(f"{API}/lifestyle", headers=headers)).json()["prestige"] == 30
    # A premium index can't be picked without owning it.
    assert (await client.patch(f"{API}/my-player", headers=headers, json={"appearance": {**LOOK, "hair": 15}})).status_code == 409
