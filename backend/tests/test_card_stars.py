"""«Звёзды карточек» (services/card_star_service.py): feeding duplicates of
the same player into one copy, the «копилка», claiming stars, refusals,
idempotency, and how the bonus reaches every game mode."""

from types import SimpleNamespace as NS

import pytest
from sqlalchemy import func, select

import app.core.rate_limit as rate_limit_module
from app.models.card import CardStarLedger, UserCard
from app.models.enums import CardSource, Position, Rarity
from app.models.game_config import GameConfig
from app.models.personal_squad import PersonalSquad, PersonalSquadCard
from app.services.card_creation import create_user_card
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/collection/cards"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _config(db_session, **overrides) -> GameConfig:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    config.card_stars_enabled = True
    # Small ladder so tests stay quick; the real defaults are 10/15/25.
    config.card_star_dupes_per_level = {r: [2, 3, 5] for r in ("common", "rare", "epic", "legendary")}
    config.card_star_coin_cost = {r: [100, 200, 400] for r in ("common", "rare", "epic", "legendary")}
    for key, value in overrides.items():
        setattr(config, key, value)
    await db_session.commit()
    return config


async def _setup(client, db_session, bot_token, telegram_id, *, copies=6, rating=80, rarity=Rarity.common, balance=10_000):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    user.balance = balance
    player = await create_player(db_session, rating=rating, rarity=rarity, position=Position.ST)
    cards = [await create_user_card(db_session, user.id, player.id, CardSource.seed) for _ in range(copies)]
    await db_session.commit()
    return headers, user, player, cards


async def _card(db_session, card_id) -> UserCard | None:
    return (
        await db_session.execute(select(UserCard).where(UserCard.id == card_id).execution_options(populate_existing=True))
    ).scalar_one_or_none()


async def _feed(client, headers, card_id, **payload):
    return await client.post(f"{API}/{card_id}/stars/feed", headers=headers, json=payload)


# --- feeding, «копилка», claiming -------------------------------------------------------------


async def test_feed_reaches_a_star_charges_coins_and_burns_materials(client, db_session, bot_token):
    await _config(db_session)
    headers, user, _player, cards = await _setup(client, db_session, bot_token, 890001)
    target, materials = cards[0], cards[1:3]

    resp = await _feed(client, headers, target.id, material_card_ids=[m.id for m in materials])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cards_consumed"] == 2 and body["stars_gained"] == 1 and body["coins_spent"] == 100
    assert body["new_balance"] == 9_900
    state = body["state"]
    assert state["stars"] == 1 and state["progress"] == 0 and state["rating_now"] == 81
    assert state["next_threshold"] == 3 and state["next_coin_cost"] == 200
    for m in materials:
        assert await _card(db_session, m.id) is None
    card = await _card(db_session, target.id)
    assert (card.stars, card.star_progress, card.star_rating_bonus) == (1, 0, 1)
    ledger = (await db_session.execute(select(CardStarLedger))).scalars().one()
    assert ledger.kind == "feed" and ledger.consumed_card_ids == [m.id for m in materials]


async def test_kopilka_banks_progress_and_rolls_over(client, db_session, bot_token):
    await _config(db_session)
    headers, _user, _player, cards = await _setup(client, db_session, bot_token, 890002)
    target = cards[0]
    body = (await _feed(client, headers, target.id, material_card_ids=[cards[1].id])).json()
    assert body["state"]["stars"] == 0 and body["state"]["progress"] == 1 and body["stars_gained"] == 0
    body = (await _feed(client, headers, target.id, material_card_ids=[c.id for c in cards[2:5]])).json()
    # 1 + 3 = 4: star 1 takes 2, the other 2 roll over toward star 2 (needs 3).
    assert body["state"]["stars"] == 1 and body["state"]["progress"] == 2


async def test_without_coins_progress_waits_and_claim_takes_it_later(client, db_session, bot_token):
    await _config(db_session)
    headers, user, _player, cards = await _setup(client, db_session, bot_token, 890003, balance=50)
    target = cards[0]
    body = (await _feed(client, headers, target.id, material_card_ids=[cards[1].id, cards[2].id])).json()
    assert body["stars_gained"] == 0 and body["state"]["claimable"] is True and body["state"]["progress"] == 2

    resp = await client.post(f"{API}/{target.id}/stars/claim", headers=headers, json={})
    assert resp.status_code == 400 and resp.json()["error"]["details"]["reason"] == "insufficient_coins"

    user.balance = 500
    await db_session.commit()
    resp = await client.post(f"{API}/{target.id}/stars/claim", headers=headers, json={"idempotency_key": "c1"})
    assert resp.status_code == 200
    assert resp.json()["state"]["stars"] == 1 and resp.json()["new_balance"] == 400


async def test_feed_stops_at_max_stars_and_cap_and_99(client, db_session, bot_token):
    await _config(db_session, card_star_rating_per_star=3, card_star_bonus_cap=6)
    headers, _user, _player, cards = await _setup(client, db_session, bot_token, 890004, copies=13, rating=95)
    target = cards[0]
    resp = await _feed(client, headers, target.id, all_free=True)
    body = resp.json()
    # 2 + 3 + 5 = 10 duplicates reach the max; the other 2 stay untouched.
    assert body["cards_consumed"] == 10 and body["state"]["stars"] == 3
    card = await _card(db_session, target.id)
    assert card.star_rating_bonus == 6  # 3 stars × 3, capped at 6
    assert body["state"]["rating_now"] == 99  # 95 + 6, card kept at 99
    resp = await _feed(client, headers, target.id, all_free=True)
    assert resp.status_code == 409 and resp.json()["error"]["details"]["reason"] == "card_blocked"
    remaining = (await db_session.execute(
        select(func.count()).select_from(UserCard).where(UserCard.player_id == target.player_id)
    )).scalar_one()
    assert remaining == 3


async def test_all_free_skips_skilled_locked_squad_and_starred_copies(client, db_session, bot_token):
    await _config(db_session)
    headers, user, _player, cards = await _setup(client, db_session, bot_token, 890005, copies=7)
    target, skilled, in_lineup, in_trade, in_squad, starred, free = cards
    skilled.skill_code, skilled.skill_level = "sniper", 1
    in_lineup.is_in_lineup = True
    in_trade.is_locked_in_trade = True
    starred.star_progress = 1
    squad = PersonalSquad(user_id=user.id, template_index=1, name="T", is_active=True)
    db_session.add(squad)
    await db_session.flush()
    db_session.add(PersonalSquadCard(squad_id=squad.id, user_card_id=in_squad.id, slot_code="FWD2"))
    await db_session.commit()

    state = (await client.get(f"{API}/{target.id}/stars", headers=headers)).json()
    assert {d["id"] for d in state["free_duplicates"]} == {skilled.id, free.id}
    assert state["free_duplicates"][0]["id"] == free.id  # skill-less first

    body = (await _feed(client, headers, target.id, all_free=True)).json()
    assert body["cards_consumed"] == 1  # only `free`: all_free never burns a skill
    for c in (skilled, in_lineup, in_trade, in_squad, starred):
        assert await _card(db_session, c.id) is not None


@pytest.mark.parametrize("case", ["other_player", "in_lineup", "starred", "self"])
async def test_explicit_material_refusals(client, db_session, bot_token, case):
    await _config(db_session)
    headers, user, _player, cards = await _setup(client, db_session, bot_token, 890010 + len(case))
    target, material = cards[0], cards[1]
    if case == "other_player":
        other = await create_player(db_session, position=Position.ST)
        material = await create_user_card(db_session, user.id, other.id, CardSource.seed)
    elif case == "in_lineup":
        material.is_in_lineup = True
    elif case == "starred":
        material.stars, material.star_rating_bonus = 1, 1
    else:
        material = target
    await db_session.commit()
    resp = await _feed(client, headers, target.id, material_card_ids=[material.id])
    assert resp.status_code == 409
    assert await _card(db_session, material.id) is not None


async def test_target_refusals_diamond_foreign_trade_and_flag(client, db_session, bot_token):
    config = await _config(db_session)
    headers, _user, _player, cards = await _setup(client, db_session, bot_token, 890020, rarity=Rarity.diamond)
    resp = await _feed(client, headers, cards[0].id, all_free=True)
    assert resp.status_code == 409 and "бриллиант" in resp.json()["error"]["message"]

    other_headers, _u, _p, other_cards = await _setup(client, db_session, bot_token, 890021)
    assert (await _feed(client, headers, other_cards[0].id, all_free=True)).status_code == 404

    other_cards[0].is_locked_in_trade = True
    await db_session.commit()
    assert (await _feed(client, other_headers, other_cards[0].id, all_free=True)).status_code == 409

    config.card_stars_enabled = False
    await db_session.commit()
    resp = await _feed(client, other_headers, other_cards[1].id, all_free=True)
    assert resp.status_code == 409 and "отключены" in resp.json()["error"]["message"]


async def test_skilled_material_needs_confirmation(client, db_session, bot_token):
    await _config(db_session)
    headers, _user, _player, cards = await _setup(client, db_session, bot_token, 890030)
    cards[1].skill_code, cards[1].skill_level = "sniper", 2
    await db_session.commit()
    resp = await _feed(client, headers, cards[0].id, material_card_ids=[cards[1].id])
    assert resp.status_code == 409 and resp.json()["error"]["details"]["requires_skill_loss_confirmation"] is True
    resp = await _feed(client, headers, cards[0].id, material_card_ids=[cards[1].id], confirm_skill_loss=True)
    assert resp.status_code == 200 and resp.json()["cards_consumed"] == 1


async def test_same_idempotency_key_replays_without_second_charge(client, db_session, bot_token):
    await _config(db_session)
    headers, _user, _player, cards = await _setup(client, db_session, bot_token, 890031)
    payload = {"material_card_ids": [cards[1].id, cards[2].id], "idempotency_key": "feed-1"}
    first = (await _feed(client, headers, cards[0].id, **payload)).json()
    second = (await _feed(client, headers, cards[0].id, **payload)).json()
    assert first["replayed"] is False and second["replayed"] is True
    assert second["new_balance"] == first["new_balance"] == 9_900
    assert second["state"]["stars"] == 1
    assert (await db_session.execute(select(func.count()).select_from(CardStarLedger))).scalar_one() == 1


async def test_flag_off_keeps_earned_stars_working(client, db_session, bot_token):
    config = await _config(db_session)
    headers, _user, _player, cards = await _setup(client, db_session, bot_token, 890032)
    await _feed(client, headers, cards[0].id, material_card_ids=[cards[1].id, cards[2].id])
    config.card_stars_enabled = False
    await db_session.commit()
    items = (await client.get("/api/v1/collection/cards", headers=headers)).json()["items"]
    # The starred copy is its own list item (pickers must be able to choose
    # exactly it); the plain spares stay collapsed into another one.
    item = next(i for i in items if i["id"] == cards[0].id)
    assert sum(1 for i in items if i["player"]["id"] == cards[0].player_id) == 2
    assert item["player"]["rating"] == 81 and item["stars"] == 1 and item["star_rating_bonus"] == 1


# --- the bonus in every mode ------------------------------------------------------------------


def test_card_rating_bonus_reaches_every_mode():
    from app.services import auto_squad_service, career_service, stratego_service, tactico_service
    from app.services.lineup_service import FORMATION_SLOTS, calculate_base_strength
    from app.services.player_stats_service import card_rating_bonus, effective_card_stats
    from app.services.player_tournament_simulation_service import _engine_card

    player = NS(
        id=1, display_name="P", position=Position.ST, rating=80, rarity=Rarity.common, club="C", country="X",
        attack_rating=84, defense_rating=60, image_path=None,
    )
    plain = NS(id=1, player_id=1, player=player, diamond_rating_bonus=0, star_rating_bonus=0, skill_code=None, skill_level=None)
    starred = NS(**{**plain.__dict__, "star_rating_bonus": 2})

    assert card_rating_bonus(starred) == 2
    assert effective_card_stats(player, 2) == (82, 86, 61)  # attack/defense scale with the rating
    assert effective_card_stats(player, 0) == (80, 84, 60)
    assert auto_squad_service._effective(starred) == 82 and career_service._effective(starred) == 82
    assert _engine_card(starred).player.rating == 82
    assert stratego_service._card_info(starred)["power"] == 82
    assert tactico_service._card_snapshot(player, 1, card_rating_bonus(starred))["rating"] == 82
    st_slot = next(s for s in FORMATION_SLOTS if s.code == "FWD2")
    assert calculate_base_strength([(starred, st_slot)]) > calculate_base_strength([(plain, st_slot)])


# --- neighbouring mechanics --------------------------------------------------------------------


async def test_sell_duplicates_protects_star_cards_and_their_material(client, db_session, bot_token):
    await _config(db_session)
    headers, _user, _player, cards = await _setup(client, db_session, bot_token, 890040, copies=4)
    await _feed(client, headers, cards[0].id, material_card_ids=[cards[1].id])  # progress 1
    preview = (await client.post(f"{API}/sell-duplicates", headers=headers, json={"preview": True})).json()
    assert preview["sold_count"] == 0
    preview = (await client.post(
        f"{API}/sell-duplicates", headers=headers, json={"preview": True, "include_star_material": True},
    )).json()
    assert preview["sold_count"] == 2  # the two spares; the invested copy is always kept


async def test_selling_a_starred_card_needs_confirmation(client, db_session, bot_token):
    await _config(db_session)
    headers, _user, _player, cards = await _setup(client, db_session, bot_token, 890041, copies=4)
    await _feed(client, headers, cards[0].id, material_card_ids=[cards[1].id, cards[2].id])
    resp = await client.post(f"{API}/sell", headers=headers, json={"user_card_id": cards[0].id, "confirm_last_copy": True})
    details = resp.json()["error"]["details"]
    assert resp.status_code == 409 and details["requires_star_loss_confirmation"] is True
    assert details["cards"][0]["stars"] == 1
    resp = await client.post(
        f"{API}/sell", headers=headers,
        json={"user_card_id": cards[0].id, "confirm_last_copy": True, "confirm_skill_loss": True},
    )
    assert resp.status_code == 200


async def test_stars_travel_with_the_card_row(client, db_session, bot_token):
    await _config(db_session)
    headers, _user, _player, cards = await _setup(client, db_session, bot_token, 890042)
    await _feed(client, headers, cards[0].id, material_card_ids=[cards[1].id, cards[2].id])
    _h, buyer, _p, _c = await _setup(client, db_session, bot_token, 890043, copies=0)
    card = await _card(db_session, cards[0].id)
    card.owner_id = buyer.id  # what an accepted trade does to the row
    await db_session.commit()
    card = await _card(db_session, cards[0].id)
    assert (card.owner_id, card.stars, card.star_rating_bonus) == (buyer.id, 1, 1)
