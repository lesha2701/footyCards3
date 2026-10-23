"""«Экипировка» (services/equipment_service.py): shop, inventory, wearing
things on cards, how their small bonuses reach the game modes, trades and
admin edits."""

from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.card import UserCard
from app.models.enums import CardSource, Position, Rarity
from app.models.equipment import EquipmentCollection, EquipmentItem, UserEquipment
from app.models.game_config import GameConfig
from app.services import equipment_service
from app.services.card_creation import create_user_card
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/equipment"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _config(db_session, **overrides) -> GameConfig:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    config.equipment_enabled = True
    for key, value in overrides.items():
        setattr(config, key, value)
    await db_session.commit()
    return config


async def _item(db_session, **kw) -> EquipmentItem:
    defaults = dict(name="Вещь", slot="boots", rarity="rare", effect="rating", effect_value=1, coins_price=100)
    defaults.update(kw)
    item = EquipmentItem(**defaults)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def _user(client, db_session, bot_token, telegram_id, balance=10_000, position=Position.ST, **player_kw):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    user.balance = balance
    player = await create_player(db_session, rating=80, position=position, **player_kw)
    card = await create_user_card(db_session, user.id, player.id, CardSource.seed)
    await db_session.commit()
    return headers, user, card


async def _buy(client, headers, item_id, key=None):
    return await client.post(f"{API}/items/{item_id}/buy", headers=headers, json={"idempotency_key": key})


async def _card(db_session, card_id) -> UserCard:
    return (await db_session.execute(
        select(UserCard).where(UserCard.id == card_id).execution_options(populate_existing=True)
    )).scalar_one()


# --- effects ----------------------------------------------------------------------------------


def test_effects_sum_conditions_sets_and_caps():
    config = NS(equipment_enabled=True, equipment_max_rating=3, equipment_max_pp=8, equipment_max_chemistry=1)
    retro = NS(id=1, is_active=True, set_size=3, set_bonus_rating=1)
    st = NS(position=Position.ST, club="Реал", country="Испания")

    def it(slot, effect, value, collection=None, **kw):
        return NS(slot=slot, effect=effect, effect_value=value, collection_id=collection.id if collection else None,
                  collection=collection, cond_club=kw.get("club"), cond_country=kw.get("country"))

    items = [it("boots", "shot_pp", 3, retro), it("kit", "rating", 1, retro), it("socks", "dribble_pp", 2, retro)]
    # Full «Ретро» set: +1 rating from the kit, +1 set bonus.
    assert equipment_service.compute_effects(st, items, config) == (2, 0, {"shot_pp": 3, "dribble_pp": 2})
    # Caps: rating 3, pp 8, chemistry 1.
    heavy = [it("kit", "rating", 5), it("boots", "shot_pp", 20), it("accessory", "chemistry", 2)]
    assert equipment_service.compute_effects(st, heavy, config) == (3, 1, {"shot_pp": 8})
    # «Родная форма» of another club / gloves on a striker: worn, but nothing.
    assert equipment_service.compute_effects(st, [it("kit", "rating", 1, club="Барселона")], config) == (0, 0, None)
    assert equipment_service.compute_effects(st, [it("kit", "rating", 1, club=" реал ")], config) == (1, 0, None)
    assert equipment_service.compute_effects(st, [it("gloves", "rating", 1)], config) == (0, 0, None)
    # Switched off: nothing at all.
    off = NS(**{**config.__dict__, "equipment_enabled": False})
    assert equipment_service.compute_effects(st, items, off) == (0, 0, None)


# --- shop and inventory -----------------------------------------------------------------------


async def test_buy_for_coins_is_idempotent_and_lists_in_inventory(client, db_session, bot_token):
    await _config(db_session)
    item = await _item(db_session, coins_price=300)
    headers, user, _card_row = await _user(client, db_session, bot_token, 910001)
    first = (await _buy(client, headers, item.id, "k1")).json()
    again = (await _buy(client, headers, item.id, "k1")).json()
    assert first["new_balance"] == 9_700 and again["replayed"] is True and again["copy_id"] == first["copy_id"]
    inv = (await client.get(f"{API}/inventory", headers=headers)).json()
    assert len(inv["items"]) == 1 and inv["items"][0]["item"]["effect_label"] == "+1 к рейтингу"
    shop = (await client.get(f"{API}/shop", headers=headers)).json()
    assert shop["singles"][0]["owned"] == 1


async def test_buy_refusals(client, db_session, bot_token):
    config = await _config(db_session)
    stars_only = await _item(db_session, coins_price=0, stars_price=50)
    headers, user, _ = await _user(client, db_session, bot_token, 910002, balance=10)
    assert (await _buy(client, headers, stars_only.id)).status_code == 409
    cheap = await _item(db_session, coins_price=100)
    assert (await _buy(client, headers, cheap.id)).status_code == 400  # not enough coins
    config.equipment_enabled = False
    await db_session.commit()
    user.balance = 1000
    await db_session.commit()
    assert (await _buy(client, headers, cheap.id)).status_code == 409


async def test_stars_purchase_validates_and_delivers(client, db_session, bot_token):
    await _config(db_session)
    item = await _item(db_session, coins_price=0, stars_price=150, slot="artifact")
    _h, user, _ = await _user(client, db_session, bot_token, 910003)
    assert await equipment_service.validate_stars(db_session, user.id, item.id, 150) == (True, "")
    ok, _msg = await equipment_service.validate_stars(db_session, user.id, item.id, 100)
    assert not ok
    await equipment_service.deliver_stars(db_session, user, item.id)
    await db_session.commit()
    rows = (await db_session.execute(select(UserEquipment).where(UserEquipment.user_id == user.id))).scalars().all()
    assert len(rows) == 1 and rows[0].source == "stars"


# --- wearing ----------------------------------------------------------------------------------


async def test_equip_applies_bonus_swaps_slot_and_moves_between_cards(client, db_session, bot_token):
    await _config(db_session)
    kit = await _item(db_session, slot="kit", effect="rating", effect_value=1)
    better_kit = await _item(db_session, slot="kit", effect="rating", effect_value=2)
    boots = await _item(db_session, slot="boots", effect="shot_pp", effect_value=3)
    headers, user, card = await _user(client, db_session, bot_token, 910004)
    other_player = await create_player(db_session, rating=70, position=Position.ST)
    other = await create_user_card(db_session, user.id, other_player.id, CardSource.seed)
    await db_session.commit()
    copy_kit = (await _buy(client, headers, kit.id)).json()["copy_id"]
    copy_better = (await _buy(client, headers, better_kit.id)).json()["copy_id"]
    copy_boots = (await _buy(client, headers, boots.id)).json()["copy_id"]

    state = (await client.post(f"{API}/equip", headers=headers, json={"copy_id": copy_kit, "user_card_id": card.id})).json()
    assert state["rating_bonus"] == 1
    await client.post(f"{API}/equip", headers=headers, json={"copy_id": copy_boots, "user_card_id": card.id})
    c = await _card(db_session, card.id)
    assert (c.equipment_rating_bonus, c.equipment_boosts) == (1, {"shot_pp": 3})

    # Same slot: the better kit replaces the old one, which goes back to the inventory.
    state = (await client.post(f"{API}/equip", headers=headers, json={"copy_id": copy_better, "user_card_id": card.id})).json()
    kit_slot = next(s for s in state["slots"] if s["code"] == "kit")
    assert state["rating_bonus"] == 2 and kit_slot["worn"]["copy_id"] == copy_better
    assert any(o["copy_id"] == copy_kit for o in kit_slot["options"])

    # Moving the boots to another card takes them off the first one.
    await client.post(f"{API}/equip", headers=headers, json={"copy_id": copy_boots, "user_card_id": other.id})
    assert (await _card(db_session, card.id)).equipment_boosts is None
    assert (await _card(db_session, other.id)).equipment_boosts == {"shot_pp": 3}

    # The collection shows the rating with the kit on.
    items = (await client.get("/api/v1/collection/cards", headers=headers)).json()["items"]
    item = next(i for i in items if i["id"] == card.id)
    assert item["player"]["rating"] == 82 and item["equipment_rating_bonus"] == 2

    await client.post(f"{API}/unequip", headers=headers, json={"copy_id": copy_better})
    assert (await _card(db_session, card.id)).equipment_rating_bonus == 0


async def test_equip_refusals(client, db_session, bot_token):
    await _config(db_session)
    gloves = await _item(db_session, slot="gloves")
    headers, user, card = await _user(client, db_session, bot_token, 910005)
    copy_gloves = (await _buy(client, headers, gloves.id)).json()["copy_id"]
    resp = await client.post(f"{API}/equip", headers=headers, json={"copy_id": copy_gloves, "user_card_id": card.id})
    assert resp.status_code == 409 and "вратарю" in resp.json()["error"]["message"]

    _h2, _u2, foreign = await _user(client, db_session, bot_token, 910006)
    resp = await client.post(f"{API}/equip", headers=headers, json={"copy_id": copy_gloves, "user_card_id": foreign.id})
    assert resp.status_code == 404

    _h3, _u3, gk_card = await _user(client, db_session, bot_token, 910007, position=Position.GK)
    gk_card = await _card(db_session, gk_card.id)
    gk_card.owner_id = user.id
    gk_card.is_locked_in_trade = True
    await db_session.commit()
    resp = await client.post(f"{API}/equip", headers=headers, json={"copy_id": copy_gloves, "user_card_id": gk_card.id})
    assert resp.status_code == 409
    gk_card.is_locked_in_trade = False
    await db_session.commit()
    resp = await client.post(f"{API}/equip", headers=headers, json={"copy_id": copy_gloves, "user_card_id": gk_card.id})
    assert resp.status_code == 200 and resp.json()["rating_bonus"] == 1


async def test_trade_takes_things_off_and_sold_card_frees_them(client, db_session, bot_token):
    await _config(db_session)
    kit = await _item(db_session, slot="kit")
    headers, user, card = await _user(client, db_session, bot_token, 910008)
    copy_id = (await _buy(client, headers, kit.id)).json()["copy_id"]
    await client.post(f"{API}/equip", headers=headers, json={"copy_id": copy_id, "user_card_id": card.id})

    await equipment_service.detach_from_cards(db_session, [card.id])
    await db_session.commit()
    c = await _card(db_session, card.id)
    assert c.equipment_rating_bonus == 0
    row = await db_session.get(UserEquipment, copy_id)
    assert row.user_card_id is None and row.user_id == user.id

    await client.post(f"{API}/equip", headers=headers, json={"copy_id": copy_id, "user_card_id": card.id})
    await db_session.delete(await _card(db_session, card.id))  # sold / burned
    await db_session.commit()
    inv = (await client.get(f"{API}/inventory", headers=headers)).json()
    assert inv["items"][0]["user_card_id"] is None


# --- game modes -------------------------------------------------------------------------------


def test_bonus_reaches_chemistry_engine_and_rating():
    from app.services.chemistry_service import ChemistryRules, compute_chemistry
    from app.services.lineup_service import FORMATION_SLOTS
    from app.services.player_stats_service import card_rating_bonus
    from app.services.player_tournament_simulation_service import _engine_card

    player = NS(id=1, display_name="P", position=Position.ST, rating=80, rarity=Rarity.common, club="C", country="X",
                attack_rating=80, defense_rating=60, image_path=None)
    card = NS(id=1, player_id=1, player=player, diamond_rating_bonus=0, star_rating_bonus=0, path_rating_bonus=0,
              equipment_rating_bonus=2, equipment_chemistry=1, equipment_boosts={"shot_pp": 3},
              skill_code=None, skill_level=None)
    assert card_rating_bonus(card) == 2
    engine = _engine_card(card)
    assert engine.player.rating == 82 and engine.boosts == {"shot_pp": 3}
    st = next(s for s in FORMATION_SLOTS if s.code == "FWD2")
    result = compute_chemistry([(card, st)], "4-3-3", ChemistryRules(player_floor=0))
    assert result.players["FWD2"].points == 1  # no links, +1 from the armband


# --- admin ------------------------------------------------------------------------------------


async def _admin_auth(client, bot_token):
    session = await client.post("/api/v1/auth/session", headers=telegram_headers(999000001, bot_token))
    return {"Authorization": f"Bearer {session.json()['admin_token']}"}


async def test_admin_edits_catalog_and_recomputes_worn_bonuses(client, db_session, bot_token):
    await _config(db_session)
    admin = await _admin_auth(client, bot_token)
    resp = await client.post("/api/v1/admin/equipment/collections", headers=admin,
                             json={"name": "Тест", "set_size": 2, "set_bonus_rating": 1})
    collection_id = resp.json()["id"]
    payload = {"name": "Бутсы", "slot": "boots", "rarity": "epic", "collection_id": collection_id,
               "effect": "rating", "effect_value": 1, "coins_price": 100}
    item = (await client.post("/api/v1/admin/equipment/items", headers=admin, json=payload)).json()
    assert (await client.post("/api/v1/admin/equipment/items", headers=admin,
                              json={**payload, "slot": "hat"})).status_code == 409

    headers, user, card = await _user(client, db_session, bot_token, 910009)
    copy_id = (await _buy(client, headers, item["id"])).json()["copy_id"]
    await client.post(f"{API}/equip", headers=headers, json={"copy_id": copy_id, "user_card_id": card.id})
    assert (await _card(db_session, card.id)).equipment_rating_bonus == 1

    await client.put(f"/api/v1/admin/equipment/items/{item['id']}", headers=admin, json={**payload, "effect_value": 3})
    assert (await _card(db_session, card.id)).equipment_rating_bonus == 3

    catalog = (await client.get("/api/v1/admin/equipment", headers=admin)).json()
    assert {s["code"] for s in catalog["slots"]} == set(equipment_service.SLOTS)

    # Switching the mechanic off in the game config zeroes worn bonuses.
    config = (await client.get("/api/v1/admin/games/config", headers=admin)).json()
    resp = await client.put("/api/v1/admin/games/config", headers=admin, json={**config, "equipment_enabled": False})
    assert resp.status_code == 200
    assert (await _card(db_session, card.id)).equipment_rating_bonus == 0
