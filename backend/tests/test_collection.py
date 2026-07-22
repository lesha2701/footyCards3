from app.models.enums import CardSource, Rarity
from app.services.card_creation import create_user_card
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def test_sell_card_credits_quick_sell_price(client, db_session, bot_token):
    headers = telegram_headers(720001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 720001)

    player = await create_player(db_session, rarity=Rarity.common, quick_sell_price=15)
    await create_user_card(db_session, user.id, player.id, CardSource.seed)
    another = await create_user_card(db_session, user.id, player.id, CardSource.seed)
    await db_session.commit()

    resp = await client.post("/api/v1/collection/cards/sell", headers=headers, json={"user_card_id": another.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["coins_earned"] == 15
    assert body["new_balance"] == 515


async def test_selling_last_copy_requires_confirmation(client, db_session, bot_token):
    headers = telegram_headers(720002, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 720002)

    player = await create_player(db_session, rarity=Rarity.rare, quick_sell_price=30)
    card = await create_user_card(db_session, user.id, player.id, CardSource.seed)
    await db_session.commit()

    resp = await client.post("/api/v1/collection/cards/sell", headers=headers, json={"user_card_id": card.id})
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["requires_confirmation"] is True

    resp2 = await client.post(
        "/api/v1/collection/cards/sell", headers=headers, json={"user_card_id": card.id, "confirm_last_copy": True}
    )
    assert resp2.status_code == 200


async def test_cannot_sell_card_locked_in_lineup(client, db_session, bot_token):
    headers = telegram_headers(720003, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 720003)

    player = await create_player(db_session, rarity=Rarity.common)
    card = await create_user_card(db_session, user.id, player.id, CardSource.seed)
    card.is_in_lineup = True
    db_session.add(card)
    await db_session.commit()

    resp = await client.post("/api/v1/collection/cards/sell", headers=headers, json={"user_card_id": card.id})
    assert resp.status_code == 409
