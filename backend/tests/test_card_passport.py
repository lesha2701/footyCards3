"""«Паспорт карты» (GET /collection/cards/{id}/passport): the copy's
owners come from accepted trades and sold market lots, in order."""
from datetime import datetime, timedelta, timezone

from app.models.auction import AuctionLot
from app.models.enums import CardSource, Rarity, TradeCardSide, TradeStatus
from app.models.trade import TradeOffer, TradeOfferCard
from app.services.card_creation import create_user_card
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token, first_name):
    headers = telegram_headers(telegram_id, bot_token, first_name=first_name)
    await client.post("/api/v1/auth/session", headers=headers)
    return await get_user_by_telegram_id(db_session, telegram_id), headers


async def test_passport_follows_the_card_through_a_trade_and_a_sale(client, db_session, bot_token):
    anna, anna_h = await _register(client, db_session, 740001, bot_token, "Анна")
    boris, _ = await _register(client, db_session, 740002, bot_token, "Борис")
    vera, vera_h = await _register(client, db_session, 740003, bot_token, "Вера")
    player = await create_player(db_session, rarity=Rarity.legendary)
    first = await create_user_card(db_session, anna.id, player.id, CardSource.pack)  # №1 stays with Анна
    card = await create_user_card(db_session, anna.id, player.id, CardSource.pack)
    await db_session.flush()
    card.arena_goals = 4

    t0 = datetime.now(timezone.utc) - timedelta(days=3)
    offer = TradeOffer(
        sender_id=anna.id, receiver_id=boris.id, status=TradeStatus.accepted,
        expires_at=t0 + timedelta(days=1), resolved_at=t0,
    )
    db_session.add(offer)
    await db_session.flush()
    db_session.add(TradeOfferCard(trade_offer_id=offer.id, user_card_id=card.id, side=TradeCardSide.offered))
    db_session.add(AuctionLot(
        seller_id=boris.id, user_card_id=card.id, player_id=player.id, status="sold", kind="fixed",
        start_price=100, buy_now_price=100, fee_pct=5, duration_hours=24,
        ends_at=t0 + timedelta(days=2), closed_at=t0 + timedelta(days=1), winner_id=vera.id, final_price=100,
    ))
    card.owner_id = vera.id
    await db_session.commit()

    resp = await client.get(f"/api/v1/collection/cards/{card.id}/passport", headers=vera_h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [o["name"] for o in body["owners"]] == ["Анна", "Борис", "Вера"]
    assert [o["via"] for o in body["owners"]] == [None, "trade", "market"]
    assert body["owners"][-1]["is_you"] is True
    assert body["serial_number"] == card.serial_number and body["printed"] >= 2
    assert body["arena_goals"] == 4
    assert body["number_one_owner"] == "Анна" and body["number_one_is_you"] is False
    assert first.serial_number == 1

    # Someone else's card stays private.
    assert (await client.get(f"/api/v1/collection/cards/{card.id}/passport", headers=anna_h)).status_code == 404


async def test_a_card_that_never_moved_has_one_owner(client, db_session, bot_token):
    anna, anna_h = await _register(client, db_session, 740011, bot_token, "Анна")
    player = await create_player(db_session, rarity=Rarity.rare)
    card = await create_user_card(db_session, anna.id, player.id, CardSource.pack)
    await db_session.commit()
    body = (await client.get(f"/api/v1/collection/cards/{card.id}/passport", headers=anna_h)).json()
    assert [(o["name"], o["is_you"]) for o in body["owners"]] == [("Анна", True)]
    assert body["number_one_is_you"] is True
