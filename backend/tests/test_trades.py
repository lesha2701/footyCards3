import pytest

import app.core.rate_limit as rate_limit_module
from app.config import get_settings
from app.models.card import UserCard
from app.models.enums import CardSource, Rarity
from app.services.card_creation import create_user_card
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

settings = get_settings()


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    # create_offer/accept_offer are rate-limited per user.id, and SQLite's
    # per-test fresh DB restarts auto-increment ids at 1 — so tests sharing
    # "user #1" as the trade sender share one bucket across the whole file
    # without this (see test_packs.py's identical fixture/comment).
    rate_limit_module._hits.clear()
    yield


async def _register(client, db_session, telegram_id, bot_token, username=None):
    headers = telegram_headers(telegram_id, bot_token, username=username)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    return user, headers


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {token}"}


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


async def test_cannot_offer_a_diamond_card(client, db_session, bot_token):
    sender, sender_headers = await _register(client, db_session, 730091, bot_token)
    receiver, _ = await _register(client, db_session, 730092, bot_token)

    player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    card = await create_user_card(db_session, sender.id, player.id, CardSource.seed)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/trades/offers", headers=sender_headers,
        json={"receiver_id": receiver.id, "offered_card_ids": [card.id], "requested_card_ids": []},
    )
    assert resp.status_code == 409

    await db_session.refresh(card)
    assert card.is_locked_in_trade is False


async def test_cannot_request_a_diamond_card(client, db_session, bot_token):
    sender, sender_headers = await _register(client, db_session, 730093, bot_token)
    receiver, _ = await _register(client, db_session, 730094, bot_token)

    player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    card = await create_user_card(db_session, receiver.id, player.id, CardSource.seed)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/trades/offers", headers=sender_headers,
        json={"receiver_id": receiver.id, "offered_card_ids": [], "requested_card_ids": [card.id]},
    )
    assert resp.status_code == 409

    await db_session.refresh(card)
    assert card.is_locked_in_trade is False


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
    # so the frontend can update the displayed balance without a full reload
    assert accept_resp.json()["new_balance"] == 500 + 20

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


async def test_trade_banned_sender_cannot_create_offer(client, db_session, bot_token):
    sender, sender_headers = await _register(client, db_session, 730016, bot_token)
    receiver, _ = await _register(client, db_session, 730017, bot_token)
    sender.is_trade_banned = True
    db_session.add(sender)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/trades/offers", headers=sender_headers,
        json={"receiver_id": receiver.id, "sender_coins": 10},
    )
    assert resp.status_code == 403


async def test_cannot_create_offer_to_trade_banned_receiver(client, db_session, bot_token):
    _sender, sender_headers = await _register(client, db_session, 730018, bot_token)
    receiver, _ = await _register(client, db_session, 730019, bot_token)
    receiver.is_trade_banned = True
    db_session.add(receiver)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/trades/offers", headers=sender_headers,
        json={"receiver_id": receiver.id, "sender_coins": 10},
    )
    assert resp.status_code == 409


async def test_trade_banned_receiver_cannot_accept_offer(client, db_session, bot_token):
    _sender, sender_headers = await _register(client, db_session, 730020, bot_token)
    receiver, receiver_headers = await _register(client, db_session, 730021, bot_token)

    create_resp = await client.post(
        "/api/v1/trades/offers", headers=sender_headers,
        json={"receiver_id": receiver.id, "sender_coins": 10},
    )
    offer_id = create_resp.json()["id"]

    receiver.is_trade_banned = True
    db_session.add(receiver)
    await db_session.commit()

    resp = await client.post(f"/api/v1/trades/offers/{offer_id}/accept", headers=receiver_headers)
    assert resp.status_code == 403


async def test_trade_offer_rejects_more_than_max_cards_per_side(client, db_session, bot_token):
    sender, sender_headers = await _register(client, db_session, 730008, bot_token)
    receiver, _ = await _register(client, db_session, 730009, bot_token)

    player = await create_player(db_session, rarity=Rarity.common)
    cards = [await create_user_card(db_session, sender.id, player.id, CardSource.seed) for _ in range(4)]
    await db_session.commit()

    resp = await client.post(
        "/api/v1/trades/offers", headers=sender_headers,
        json={"receiver_id": receiver.id, "offered_card_ids": [c.id for c in cards], "requested_card_ids": []},
    )
    assert resp.status_code == 422


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


async def test_admin_can_search_trades_by_either_side_username(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    sender, sender_headers = await _register(client, db_session, 730010, bot_token, username="alice_trader")
    receiver, _ = await _register(client, db_session, 730011, bot_token, username="bob_trader")
    stranger, stranger_headers = await _register(client, db_session, 730012, bot_token, username="carol_unrelated")

    player = await create_player(db_session, rarity=Rarity.common)
    card = await create_user_card(db_session, sender.id, player.id, CardSource.seed)
    await db_session.commit()
    await client.post(
        "/api/v1/trades/offers", headers=sender_headers,
        json={"receiver_id": receiver.id, "offered_card_ids": [card.id]},
    )

    other_player = await create_player(db_session, rarity=Rarity.common)
    other_card = await create_user_card(db_session, stranger.id, other_player.id, CardSource.seed)
    await db_session.commit()
    await client.post(
        "/api/v1/trades/offers", headers=stranger_headers,
        json={"receiver_id": receiver.id, "offered_card_ids": [other_card.id]},
    )

    # Searching for the sender finds their trade.
    by_sender = await client.get("/api/v1/admin/trades", headers=auth, params={"username": "alice"})
    assert by_sender.status_code == 200
    assert len(by_sender.json()) == 1
    assert by_sender.json()[0]["sender"]["id"] == sender.id

    # Searching for the receiver finds both trades they're party to.
    by_receiver = await client.get("/api/v1/admin/trades", headers=auth, params={"username": "bob_trader"})
    assert by_receiver.status_code == 200
    assert len(by_receiver.json()) == 2

    # No match returns an empty list, not an error.
    no_match = await client.get("/api/v1/admin/trades", headers=auth, params={"username": "nobody_at_all"})
    assert no_match.status_code == 200
    assert no_match.json() == []
