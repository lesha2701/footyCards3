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


async def test_cannot_sell_card_locked_in_tactico_squad(client, db_session, bot_token):
    headers = telegram_headers(720005, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 720005)

    player = await create_player(db_session, rarity=Rarity.common)
    card = await create_user_card(db_session, user.id, player.id, CardSource.seed)
    card.is_in_tactico_squad = True
    db_session.add(card)
    await db_session.commit()

    resp = await client.post("/api/v1/collection/cards/sell", headers=headers, json={"user_card_id": card.id})
    assert resp.status_code == 409


async def test_rarity_filter_only_returns_matching_rarity(client, db_session, bot_token):
    headers = telegram_headers(720004, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 720004)

    common_player = await create_player(db_session, rarity=Rarity.common)
    rare_player = await create_player(db_session, rarity=Rarity.rare)
    await create_user_card(db_session, user.id, common_player.id, CardSource.seed)
    await create_user_card(db_session, user.id, rare_player.id, CardSource.seed)
    await db_session.commit()

    resp = await client.get("/api/v1/collection/cards", headers=headers, params={"rarity": "common"})
    assert resp.status_code == 200
    body = resp.json()
    assert {item["player"]["rarity"] for item in body["items"]} == {"common"}


async def test_duplicate_cards_collapse_into_one_list_row(client, db_session, bot_token):
    headers = telegram_headers(720005, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 720005)

    player = await create_player(db_session, rarity=Rarity.common)
    for _ in range(3):
        await create_user_card(db_session, user.id, player.id, CardSource.seed)
    await db_session.commit()

    resp = await client.get("/api/v1/collection/cards", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["duplicate_count"] == 3


async def test_collection_list_exposes_tactico_squad_lock(client, db_session, bot_token):
    """The frontend can't filter Tactico-squad cards out of trade offers
    (or show a lock badge for them) if the collection listing never tells
    it which cards are squadded in the first place."""
    headers = telegram_headers(720006, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 720006)

    player = await create_player(db_session, rarity=Rarity.common)
    card = await create_user_card(db_session, user.id, player.id, CardSource.seed)
    card.is_in_tactico_squad = True
    db_session.add(card)
    await db_session.commit()

    resp = await client.get("/api/v1/collection/cards", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["is_in_tactico_squad"] is True
