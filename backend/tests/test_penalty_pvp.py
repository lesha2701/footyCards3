from app.models.card import UserCard
from app.models.enums import CardSource, Rarity
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def _grant_card(db_session, owner_id: int, rating: int = 80) -> UserCard:
    player = await create_player(db_session, rarity=Rarity.rare, rating=rating)
    card = UserCard(owner_id=owner_id, player_id=player.id, source=CardSource.seed)
    db_session.add(card)
    await db_session.flush()
    card.serial_number = card.id
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)
    return card


async def test_penalty_challenge_create_and_accept(client, db_session, bot_token):
    sender = await _register(client, db_session, 860101, bot_token)
    receiver = await _register(client, db_session, 860102, bot_token)
    sender_card = await _grant_card(db_session, sender.id)
    receiver_card = await _grant_card(db_session, receiver.id)
    sender_headers = telegram_headers(860101, bot_token)
    receiver_headers = telegram_headers(860102, bot_token)

    resp = await client.post(
        "/api/v1/games/penalty/challenges", headers=sender_headers,
        json={"opponent_user_id": receiver.id, "user_card_id": sender_card.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending_accept"
    assert body["viewer_side"] == "user"
    match_id = body["id"]

    accept = await client.post(
        f"/api/v1/games/penalty/challenges/{match_id}/accept", headers=receiver_headers,
        json={"user_card_id": receiver_card.id},
    )
    assert accept.status_code == 200
    accepted_body = accept.json()
    assert accepted_body["status"] == "in_progress"
    assert accepted_body["viewer_side"] == "opponent"
    assert accepted_body["kicker"] == "opponent"  # the challenger ("user" from their own view) kicks first;
    # from the accepting side's view the challenger is "opponent"
    assert accepted_body["kick_deadline"] is not None
    assert accepted_body["match_deadline"] is not None


async def test_penalty_cannot_challenge_self(client, db_session, bot_token):
    user = await _register(client, db_session, 860103, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(860103, bot_token)

    resp = await client.post(
        "/api/v1/games/penalty/challenges", headers=headers,
        json={"opponent_user_id": user.id, "user_card_id": card.id},
    )
    assert resp.status_code == 409


async def test_penalty_decline_challenge(client, db_session, bot_token):
    sender = await _register(client, db_session, 860104, bot_token)
    receiver = await _register(client, db_session, 860105, bot_token)
    sender_card = await _grant_card(db_session, sender.id)
    sender_headers = telegram_headers(860104, bot_token)
    receiver_headers = telegram_headers(860105, bot_token)

    create = await client.post(
        "/api/v1/games/penalty/challenges", headers=sender_headers,
        json={"opponent_user_id": receiver.id, "user_card_id": sender_card.id},
    )
    match_id = create.json()["id"]

    decline = await client.post(f"/api/v1/games/penalty/challenges/{match_id}/decline", headers=receiver_headers)
    assert decline.status_code == 200
    assert decline.json()["status"] == "declined"


async def test_penalty_cancel_challenge(client, db_session, bot_token):
    sender = await _register(client, db_session, 860106, bot_token)
    receiver = await _register(client, db_session, 860107, bot_token)
    sender_card = await _grant_card(db_session, sender.id)
    sender_headers = telegram_headers(860106, bot_token)

    create = await client.post(
        "/api/v1/games/penalty/challenges", headers=sender_headers,
        json={"opponent_user_id": receiver.id, "user_card_id": sender_card.id},
    )
    match_id = create.json()["id"]

    cancel = await client.post(f"/api/v1/games/penalty/challenges/{match_id}/cancel", headers=sender_headers)
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"


async def test_penalty_only_challenged_user_can_accept(client, db_session, bot_token):
    sender = await _register(client, db_session, 860108, bot_token)
    receiver = await _register(client, db_session, 860109, bot_token)
    stranger = await _register(client, db_session, 860110, bot_token)
    sender_card = await _grant_card(db_session, sender.id)
    stranger_card = await _grant_card(db_session, stranger.id)
    sender_headers = telegram_headers(860108, bot_token)
    stranger_headers = telegram_headers(860110, bot_token)

    create = await client.post(
        "/api/v1/games/penalty/challenges", headers=sender_headers,
        json={"opponent_user_id": receiver.id, "user_card_id": sender_card.id},
    )
    match_id = create.json()["id"]

    resp = await client.post(
        f"/api/v1/games/penalty/challenges/{match_id}/accept", headers=stranger_headers,
        json={"user_card_id": stranger_card.id},
    )
    assert resp.status_code == 403
