from app.models.card import UserCard
from app.models.enums import CardSource, Rarity
from app.services.card_creation import create_user_card
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    return user, headers


async def test_create_trade_locks_offered_card(client, db_session, bot_token):
    sender, sender_headers = await _register(client, db_session, 730001, bot_token)
    receiver, _ = await _register(client, db_session, 730002, bot_token)

    player = await create_player(db_session, rarity=Rarity.common)
    card = await create_user_card(db_session, sender.id, player.id, CardSource.seed)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/trades/offers", headers=sender_headers,
        json={"receiver_id": receiver.id, "offered_card_ids": [card.id], "requested_card_ids": []},
    )
    assert resp.status_code == 200

    await db_session.refresh(card)
    assert card.is_locked_in_trade is True


async def test_cannot_trade_with_self(client, db_session, bot_token):
    user, headers = await _register(client, db_session, 730003, bot_token)
    resp = await client.post(
        "/api/v1/trades/offers", headers=headers,
        json={"receiver_id": user.id, "sender_coins": 10},
    )
    assert resp.status_code == 409


async def test_accept_trade_transfers_cards_and_coins(client, db_session, bot_token):
    sender, sender_headers = await _register(client, db_session, 730004, bot_token)
    receiver, receiver_headers = await _register(client, db_session, 730005, bot_token)

    player_a = await create_player(db_session, rarity=Rarity.common)
    player_b = await create_player(db_session, rarity=Rarity.rare)
    sender_card = await create_user_card(db_session, sender.id, player_a.id, CardSource.seed)
    receiver_card = await create_user_card(db_session, receiver.id, player_b.id, CardSource.seed)
    await db_session.commit()

    create_resp = await client.post(
        "/api/v1/trades/offers", headers=sender_headers,
        json={
            "receiver_id": receiver.id,
            "offered_card_ids": [sender_card.id],
            "requested_card_ids": [receiver_card.id],
            "sender_coins": 20,
        },
    )
    offer_id = create_resp.json()["id"]

    accept_resp = await client.post(f"/api/v1/trades/offers/{offer_id}/accept", headers=receiver_headers)
    assert accept_resp.status_code == 200
    assert accept_resp.json()["status"] == "accepted"

    await db_session.refresh(sender_card)
    await db_session.refresh(receiver_card)
    assert sender_card.owner_id == receiver.id
    assert receiver_card.owner_id == sender.id
    assert sender_card.is_locked_in_trade is False

    await db_session.refresh(sender)
    await db_session.refresh(receiver)
    assert sender.balance == 500 - 20
    assert receiver.balance == 500 + 20


async def test_cannot_accept_trade_twice(client, db_session, bot_token):
    sender, sender_headers = await _register(client, db_session, 730006, bot_token)
    receiver, receiver_headers = await _register(client, db_session, 730007, bot_token)

    player = await create_player(db_session, rarity=Rarity.common)
    sender_card = await create_user_card(db_session, sender.id, player.id, CardSource.seed)
    await db_session.commit()

    create_resp = await client.post(
        "/api/v1/trades/offers", headers=sender_headers,
        json={"receiver_id": receiver.id, "offered_card_ids": [sender_card.id]},
    )
    offer_id = create_resp.json()["id"]

    first = await client.post(f"/api/v1/trades/offers/{offer_id}/accept", headers=receiver_headers)
    second = await client.post(f"/api/v1/trades/offers/{offer_id}/accept", headers=receiver_headers)

    assert first.status_code == 200
    assert second.status_code == 409


async def test_cannot_trade_with_user_who_opted_out(client, db_session, bot_token):
    sender, sender_headers = await _register(client, db_session, 730010, bot_token)
    receiver, _ = await _register(client, db_session, 730011, bot_token)
    receiver.accept_trades = False
    db_session.add(receiver)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/trades/offers", headers=sender_headers,
        json={"receiver_id": receiver.id, "sender_coins": 10},
    )
    assert resp.status_code == 409


async def test_opted_out_user_excluded_from_search(client, db_session, bot_token):
    _, headers = await _register(client, db_session, 730012, bot_token)
    hidden_user, _ = await _register(client, db_session, 730013, bot_token)
    hidden_user.username = "findme_hidden"
    hidden_user.accept_trades = False
    db_session.add(hidden_user)
    await db_session.commit()

    resp = await client.get("/api/v1/users/search?q=findme_hidden", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_cannot_request_card_hidden_from_trade(client, db_session, bot_token):
    _, sender_headers = await _register(client, db_session, 730014, bot_token)
    receiver, _ = await _register(client, db_session, 730015, bot_token)

    player = await create_player(db_session, rarity=Rarity.common)
    receiver_card = await create_user_card(db_session, receiver.id, player.id, CardSource.seed)
    receiver_card.hidden_from_trade = True
    db_session.add(receiver_card)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/trades/offers", headers=sender_headers,
        json={"receiver_id": receiver.id, "requested_card_ids": [receiver_card.id]},
    )
    assert resp.status_code == 409


async def test_hidden_card_excluded_from_public_collection(client, db_session, bot_token):
    owner, _owner_headers = await _register(client, db_session, 730016, bot_token)
    _, viewer_headers = await _register(client, db_session, 730017, bot_token)

    player = await create_player(db_session, rarity=Rarity.common)
    card = await create_user_card(db_session, owner.id, player.id, CardSource.seed)
    card.hidden_from_trade = True
    db_session.add(card)
    await db_session.commit()

    resp = await client.get(f"/api/v1/users/{owner.id}/collection", headers=viewer_headers)
    assert resp.status_code == 200
    assert resp.json()["items"] == []


async def test_cancel_trade_unlocks_cards(client, db_session, bot_token):
    sender, sender_headers = await _register(client, db_session, 730008, bot_token)
    receiver, _ = await _register(client, db_session, 730009, bot_token)

    player = await create_player(db_session, rarity=Rarity.common)
    card = await create_user_card(db_session, sender.id, player.id, CardSource.seed)
    await db_session.commit()

    create_resp = await client.post(
        "/api/v1/trades/offers", headers=sender_headers,
        json={"receiver_id": receiver.id, "offered_card_ids": [card.id]},
    )
    offer_id = create_resp.json()["id"]

    cancel_resp = await client.post(f"/api/v1/trades/offers/{offer_id}/cancel", headers=sender_headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    await db_session.refresh(card)
    assert card.is_locked_in_trade is False
