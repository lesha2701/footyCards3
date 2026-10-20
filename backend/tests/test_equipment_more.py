"""«Экипировка», part 2: save / tackle / pass effects in Card Arena and the
tournament engine, talismans (experience, Arena win coins), limited editions
with serial numbers, seasonal sale windows and the national-team set."""

import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.card import UserCard
from app.models.enums import CardSource, Position, Rarity
from app.models.equipment import EquipmentCollection, EquipmentItem, UserEquipment
from app.models.game_config import GameConfig
from app.services import equipment_service, match_service, path_service, tournament_match_engine
from app.services.card_creation import create_user_card
from app.services.chemistry_service import ChemistryRules, compute_chemistry
from app.services.lineup_service import FORMATION_SLOTS
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/equipment"
CONFIG = NS(equipment_enabled=True, equipment_max_rating=3, equipment_max_pp=8, equipment_max_chemistry=1,
            equipment_max_talisman_pct=15)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


def _it(slot, effect, value, collection=None, **kw):
    return NS(slot=slot, effect=effect, effect_value=value, collection_id=collection.id if collection else None,
              collection=collection, cond_club=kw.get("club"), cond_country=kw.get("country"))


# --- effects ----------------------------------------------------------------------------------


def test_new_effects_are_summed_and_capped():
    gk = NS(position=Position.GK, club="C", country="X")
    items = [_it("gloves", "save_pp", 5), _it("accessory", "save_pp", 6), _it("kit", "pass_pp", 3),
             _it("socks", "tackle_pp", 4), _it("artifact", "xp_pct", 20)]
    rating, chemistry, boosts = equipment_service.compute_effects(gk, items, CONFIG)
    assert (rating, chemistry) == (0, 0)
    assert boosts == {"save_pp": 8, "pass_pp": 3, "tackle_pp": 4, "xp_pct": 15}  # pp cap 8, talisman cap 15


def test_national_team_set_marks_the_card_and_needs_the_full_set():
    brazil = NS(id=5, is_active=True, set_size=3, set_bonus_rating=0, set_team_country="Бразилия", set_team_chemistry=1)
    player = NS(position=Position.ST, club="C", country="Бразилия")
    full = [_it("kit", "chemistry", 1, brazil, country="Бразилия"), _it("accessory", "dribble_pp", 3, brazil),
            _it("artifact", "coins_pct", 5, brazil)]
    _rating, chemistry, boosts = equipment_service.compute_effects(player, full, CONFIG)
    assert chemistry == 1 and boosts["team_country"] == "Бразилия" and boosts["team_chemistry"] == 1
    _r, _c, partial = equipment_service.compute_effects(player, full[:2], CONFIG)
    assert "team_country" not in (partial or {})
    # The kit only fits a Brazilian: on someone else the set is not complete.
    _r, _c, other = equipment_service.compute_effects(NS(position=Position.ST, club="C", country="Италия"), full, CONFIG)
    assert "team_country" not in (other or {})


def test_team_set_gives_chemistry_to_every_player_of_that_country():
    slots = {s.code: s for s in FORMATION_SLOTS}

    def card(code, country, boosts=None):
        return (NS(player=NS(club=f"club-{code}", country=country, position=slots[code].ideal_position),
                   equipment_chemistry=0, equipment_boosts=boosts), slots[code])

    rules = ChemistryRules(player_floor=0)
    plain = [card("FWD2", "Бразилия"), card("FWD1", "Италия"), card("GK", "Бразилия")]
    worn = [card("FWD2", "Бразилия", {"team_country": "Бразилия", "team_chemistry": 1}), card("FWD1", "Италия"),
            card("GK", "Бразилия")]
    before = compute_chemistry(plain, "4-3-3", rules)
    after = compute_chemistry(worn, "4-3-3", rules)
    assert after.players["GK"].points == before.players["GK"].points + 1
    assert after.players["FWD2"].points == before.players["FWD2"].points + 1
    assert after.players["FWD1"].points == before.players["FWD1"].points


# --- Card Arena -------------------------------------------------------------------------------


def test_arena_tackle_pass_and_save_bonuses():
    state = {"equipment": {"7": {"tackle_pp": 5, "pass_pp": 4, "save_pp": 6}}, "equipment_gk": {"id": 7, "name": "Кипер"}}
    actor = {"user_card_id": 7, "name": "Игрок"}
    notes: list = []
    adjust = match_service._equipment_adjusted
    assert adjust(state, actor, 0.30, match_service._NO_TAGS, own="tackle_pp", notes=notes) == pytest.approx(0.25)
    assert adjust(state, actor, 0.30, match_service._NO_TAGS, own="pass_pp", notes=notes) == pytest.approx(0.26)
    assert match_service._user_save_pp(state) == (6, "Кипер")
    config = GameConfig(id=1)
    for column in GameConfig.__table__.columns:
        if getattr(config, column.key) is None and column.default is not None and not callable(column.default.arg):
            setattr(config, column.key, column.default.arg)

    def saves(save_pp: int) -> int:
        random.seed(5)
        return sum(
            match_service._resolve_shot_continuation(False, "in_box", config, None, 70, save_pp=save_pp, equipment_notes=[])[0] == "save"
            for _ in range(3000)
        )

    assert saves(8) > saves(0)
    equipment_notes: list = []
    random.seed(1)
    match_service._resolve_shot_continuation(False, "in_box", config, None, 70, save_pp=6, save_player="Кипер",
                                             equipment_notes=equipment_notes)
    assert equipment_notes == [{"player": "Кипер", "effect": "save_pp", "bonus_pp": 6}]


def test_arena_coin_talismans_are_summed_and_capped():
    def slot(boosts):
        return NS(card=NS(equipment_boosts=boosts))

    lineup = NS(slots=[slot({"coins_pct": 10}), slot({"coins_pct": 10}), slot(None), NS(card=None)])
    assert match_service.equipment_coins_pct(lineup, CONFIG) == 15


# --- tournament engine ------------------------------------------------------------------------


def test_tournament_engine_boost_helpers():
    actor = {"boosts": {"save_pp": 5, "pass_pp": 4}}
    assert tournament_match_engine._boost(actor, "save_pp") == 5 and tournament_match_engine._boost(None, "save_pp") == 0
    assert tournament_match_engine._less(0.30, 4) == pytest.approx(0.26)
    assert tournament_match_engine._less(0.03, 4) == 0.02 and tournament_match_engine._less(0.30, 0) == 0.30
    assert tournament_match_engine._more(0.50, 5) == pytest.approx(0.55)
    assert tournament_match_engine._more(0.97, 5) == 0.98 and tournament_match_engine._more(0.50, 0) == 0.50


# --- shop: limited editions and seasons -------------------------------------------------------


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


async def _user(client, db_session, bot_token, telegram_id, balance=100_000):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    user.balance = balance
    await db_session.commit()
    return headers, user


async def test_limited_edition_numbers_copies_and_sells_out(client, db_session, bot_token):
    await _config(db_session)
    item = EquipmentItem(name="Золотая", slot="boots", effect="shot_pp", effect_value=6, coins_price=100, max_supply=2)
    db_session.add(item)
    await db_session.commit()
    headers, user = await _user(client, db_session, bot_token, 940001)
    for _ in range(2):
        assert (await client.post(f"{API}/items/{item.id}/buy", headers=headers, json={})).status_code == 200
    resp = await client.post(f"{API}/items/{item.id}/buy", headers=headers, json={})
    assert resp.status_code == 409 and "распродан" in resp.json()["error"]["message"]
    inventory = (await client.get(f"{API}/inventory", headers=headers)).json()["items"]
    assert sorted(i["serial_number"] for i in inventory) == [1, 2]
    shop = (await client.get(f"{API}/shop", headers=headers)).json()
    assert shop["singles"][0]["left"] == 0 and shop["singles"][0]["max_supply"] == 2
    item.stars_price = 50
    await db_session.commit()
    await db_session.refresh(item)
    ok, message = await equipment_service.validate_stars(db_session, user.id, item.id, 50)
    assert not ok and "распродан" in message


async def test_seasonal_items_are_sold_only_inside_their_window(client, db_session, bot_token):
    await _config(db_session)
    now = datetime.now(timezone.utc)
    past = EquipmentItem(name="Прошлая зима", slot="kit", effect="pass_pp", effect_value=4, coins_price=100,
                         available_until=now - timedelta(days=1))
    future = EquipmentItem(name="Будущая зима", slot="kit", effect="pass_pp", effect_value=4, coins_price=100,
                           available_from=now + timedelta(days=1))
    current = EquipmentItem(name="Эта зима", slot="kit", effect="pass_pp", effect_value=4, coins_price=100,
                            available_until=now + timedelta(days=30))
    db_session.add_all([past, future, current])
    await db_session.commit()
    headers, _user_row = await _user(client, db_session, bot_token, 940002)
    names = {i["name"] for i in (await client.get(f"{API}/shop", headers=headers)).json()["singles"]}
    assert names == {"Эта зима"}
    assert (await client.post(f"{API}/items/{past.id}/buy", headers=headers, json={})).status_code == 409
    assert (await client.post(f"{API}/items/{future.id}/buy", headers=headers, json={})).status_code == 409
    assert (await client.post(f"{API}/items/{current.id}/buy", headers=headers, json={})).status_code == 200


# --- talismans: «Академия» experience ---------------------------------------------------------


async def test_experience_talisman_adds_to_path_experience(client, db_session, bot_token):
    await _config(db_session, path_enabled=True)
    _headers, user = await _user(client, db_session, bot_token, 940003)
    player = await create_player(db_session, rarity=Rarity.diamond, rating=60, position=Position.ST, path_talent_code="big_matches")
    plain = await create_user_card(db_session, user.id, player.id, CardSource.seed)
    talisman = await create_user_card(db_session, user.id, player.id, CardSource.seed)
    talisman.equipment_boosts = {"xp_pct": 10}
    await db_session.commit()
    entries = [path_service.MatchEntry(plain.id, "win", goals=1), path_service.MatchEntry(talisman.id, "win", goals=1)]
    results = await path_service.award_match(db_session, user_id=user.id, source_type="arena", source_id="1", entries=entries)
    by_card = {r.user_card_id: r.xp for r in results}
    assert by_card[talisman.id] == by_card[plain.id] + by_card[plain.id] * 10 // 100
