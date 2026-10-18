"""«Лишние карты» клуба: sell non-squad club cards into the budget, exchange
N of one rarity for one of the next."""
import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.club import Club
from app.models.club_budget import ClubBudgetTransaction
from app.models.club_card import ClubCard
from app.models.enums import ClubBudgetTransactionType, ClubCardSource, Position, Rarity
from app.services.club_card_service import create_club_card
from app.services.game_config_service import get_config
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
async def _seed(db_session):
    rate_limit_module._hits.clear()
    for position in (Position.GK, Position.GK, Position.LB, Position.LB, Position.CB, Position.CB, Position.RB,
                     Position.RB, Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM, Position.LW,
                     Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _register(client, db_session, telegram_id, bot_token):
    headers = telegram_headers(telegram_id, bot_token)
    assert (await client.post("/api/v1/auth/session", headers=headers)).status_code == 200
    return headers, await get_user_by_telegram_id(db_session, telegram_id)


async def _club(client, db_session, bot_token, base_id):
    cap_h, _captain = await _register(client, db_session, base_id, bot_token)
    resp = await client.post("/api/v1/clubs", headers=cap_h, json={
        "name": f"Клуб {base_id}", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000",
    })
    club_id = resp.json()["id"]
    # Materialize the lineup templates (create_club leaves the starting squad in template 1).
    await client.get("/api/v1/clubs/me/lineup", headers=cap_h)
    mem_h, _member = await _register(client, db_session, base_id + 1, bot_token)
    await client.post(f"/api/v1/clubs/{club_id}/join", headers=mem_h)
    return club_id, cap_h, mem_h


async def _extra_cards(db_session, club_id, rarity, count, quick_sell=40):
    ids = []
    for _ in range(count):
        player = await create_player(db_session, rarity=rarity, quick_sell_price=quick_sell)
        card = await create_club_card(db_session, club_id, player.id, ClubCardSource.club_pack)
        ids.append(card.id)
    await db_session.commit()
    return ids


async def test_surplus_lists_squad_cards_as_protected(client, db_session, bot_token):
    club_id, cap_h, _mem_h = await _club(client, db_session, bot_token, 870000)
    extra = await _extra_cards(db_session, club_id, Rarity.rare, 2, quick_sell=50)
    body = (await client.get("/api/v1/clubs/me/surplus", headers=cap_h)).json()
    assert body["can_manage"] and body["enabled"]
    by_id = {c["card"]["id"]: c for c in body["cards"]}
    assert all(not by_id[i]["protected"] and by_id[i]["sell_value"] == 50 for i in extra)
    assert any(c["protected"] for c in body["cards"])  # the seeded starting squad
    rare = next(o for o in body["exchange_options"] if o["rarity"] == "rare")
    assert rare["target_rarity"] == "epic" and rare["available"] >= 2


async def test_sell_credits_budget_and_removes_cards(client, db_session, bot_token):
    club_id, cap_h, mem_h = await _club(client, db_session, bot_token, 870010)
    extra = await _extra_cards(db_session, club_id, Rarity.epic, 3, quick_sell=100)
    config = await get_config(db_session)
    config.club_card_sell_pct = 50
    await db_session.commit()
    budget = (await db_session.get(Club, club_id)).budget

    assert (await client.post("/api/v1/clubs/me/surplus/sell", headers=mem_h, json={"card_ids": extra})).status_code == 403

    resp = await client.post("/api/v1/clubs/me/surplus/sell", headers=cap_h, json={"card_ids": extra[:2]})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"sold": 2, "coins": 100, "budget": budget + 100}
    remaining = set((await db_session.execute(select(ClubCard.id).where(ClubCard.club_id == club_id))).scalars())
    assert extra[2] in remaining and not ({extra[0], extra[1]} & remaining)
    tx = (await db_session.execute(select(ClubBudgetTransaction).where(
        ClubBudgetTransaction.type == ClubBudgetTransactionType.card_sale,
    ))).scalar_one()
    assert tx.amount == 100

    # Already sold → not found; another club's card → not found.
    again = await client.post("/api/v1/clubs/me/surplus/sell", headers=cap_h, json={"card_ids": [extra[0]]})
    assert again.status_code == 404


async def test_squad_cards_cannot_be_sold(client, db_session, bot_token):
    _club_id, cap_h, _mem_h = await _club(client, db_session, bot_token, 870020)
    body = (await client.get("/api/v1/clubs/me/surplus", headers=cap_h)).json()
    squad_id = next(c["card"]["id"] for c in body["cards"] if c["protected"])
    resp = await client.post("/api/v1/clubs/me/surplus/sell", headers=cap_h, json={"card_ids": [squad_id]})
    assert resp.status_code == 409
    resp = await client.post("/api/v1/clubs/me/surplus/sell", headers=cap_h, json={"card_ids": [squad_id, squad_id]})
    assert resp.status_code == 409


async def test_exchange_five_for_one_of_next_rarity(client, db_session, bot_token):
    club_id, cap_h, _mem_h = await _club(client, db_session, bot_token, 870030)
    commons = await _extra_cards(db_session, club_id, Rarity.common, 5)
    await create_player(db_session, rarity=Rarity.rare)

    assert (await client.post("/api/v1/clubs/me/surplus/exchange", headers=cap_h, json={"card_ids": commons[:4]})).status_code == 409

    before = set((await db_session.execute(select(ClubCard.id).where(ClubCard.club_id == club_id))).scalars())
    resp = await client.post("/api/v1/clubs/me/surplus/exchange", headers=cap_h, json={"card_ids": commons})
    assert resp.status_code == 200, resp.text
    new_card = resp.json()["card"]
    assert new_card["player"]["rarity"] == "rare"
    remaining = set((await db_session.execute(select(ClubCard.id).where(ClubCard.club_id == club_id))).scalars())
    # SQLite may hand the new card a just-freed id, so compare the rest.
    assert new_card["id"] in remaining and not ((set(commons) - {new_card["id"]}) & remaining)
    assert len(remaining) == len(before) - 4
    row = await db_session.get(ClubCard, new_card["id"])
    assert row.source == ClubCardSource.exchange


async def test_exchange_refuses_mixed_rarity_or_empty_target_pool(client, db_session, bot_token):
    club_id, cap_h, _mem_h = await _club(client, db_session, bot_token, 870040)
    mixed = await _extra_cards(db_session, club_id, Rarity.common, 4) + await _extra_cards(db_session, club_id, Rarity.rare, 1)
    assert (await client.post("/api/v1/clubs/me/surplus/exchange", headers=cap_h, json={"card_ids": mixed})).status_code == 409

    # No legendary players exist at all → refuse, and nothing is destroyed.
    epics = await _extra_cards(db_session, club_id, Rarity.epic, 5)
    resp = await client.post("/api/v1/clubs/me/surplus/exchange", headers=cap_h, json={"card_ids": epics})
    assert resp.status_code == 409
    remaining = set((await db_session.execute(select(ClubCard.id).where(ClubCard.club_id == club_id))).scalars())
    assert set(epics) <= remaining

    legend = await _extra_cards(db_session, club_id, Rarity.legendary, 5)
    resp = await client.post("/api/v1/clubs/me/surplus/exchange", headers=cap_h, json={"card_ids": legend})
    assert resp.status_code == 409


async def test_market_switch_off(client, db_session, bot_token):
    club_id, cap_h, _mem_h = await _club(client, db_session, bot_token, 870050)
    extra = await _extra_cards(db_session, club_id, Rarity.common, 1)
    config = await get_config(db_session)
    config.club_card_market_enabled = False
    await db_session.commit()
    resp = await client.post("/api/v1/clubs/me/surplus/sell", headers=cap_h, json={"card_ids": extra})
    assert resp.status_code == 409
