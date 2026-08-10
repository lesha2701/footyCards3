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


async def _create_and_accept(client, db_session, bot_token, sender_tid, receiver_tid):
    sender = await _register(client, db_session, sender_tid, bot_token)
    receiver = await _register(client, db_session, receiver_tid, bot_token)
    sender_card = await _grant_card(db_session, sender.id, rating=99)
    receiver_card = await _grant_card(db_session, receiver.id, rating=99)
    sender_headers = telegram_headers(sender_tid, bot_token)
    receiver_headers = telegram_headers(receiver_tid, bot_token)

    create = await client.post(
        "/api/v1/games/penalty/challenges", headers=sender_headers,
        json={"opponent_user_id": receiver.id, "user_card_id": sender_card.id},
    )
    match_id = create.json()["id"]
    await client.post(
        f"/api/v1/games/penalty/challenges/{match_id}/accept", headers=receiver_headers,
        json={"user_card_id": receiver_card.id},
    )
    return match_id, sender, receiver, sender_headers, receiver_headers


async def test_penalty_pvp_full_match_resolves_with_score_and_rating(client, db_session, bot_token):
    match_id, sender, receiver, sender_headers, receiver_headers = await _create_and_accept(
        client, db_session, bot_token, 860201, 860202
    )

    # Regulation is 10 kicks; both sides always pick the same zone so every
    # kick is "saved" — deterministic, so the match always reaches a 0:0 draw
    # after 10 kicks without needing sudden death in this test.
    for i in range(10):
        kicker_headers = sender_headers if i % 2 == 0 else receiver_headers
        other_headers = receiver_headers if i % 2 == 0 else sender_headers
        r1 = await client.post(
            f"/api/v1/games/penalty/matches/{match_id}/pick", headers=kicker_headers, json={"zone": "top_left"}
        )
        assert r1.status_code == 200
        r2 = await client.post(
            f"/api/v1/games/penalty/matches/{match_id}/pick", headers=other_headers, json={"zone": "top_left"}
        )
        assert r2.status_code == 200

    final = r2.json()
    assert final["status"] == "finished"
    assert final["result"] == "draw"
    assert final["user_score"] == 0 and final["opponent_score"] == 0

    await db_session.refresh(sender)
    await db_session.refresh(receiver)
    assert sender.penalty_rating == 1  # draw = +1
    assert receiver.penalty_rating == 1


async def test_penalty_pvp_gives_no_coins(client, db_session, bot_token):
    match_id, sender, receiver, sender_headers, receiver_headers = await _create_and_accept(
        client, db_session, bot_token, 860203, 860204
    )
    balance_before = sender.balance

    for i in range(10):
        kicker_headers = sender_headers if i % 2 == 0 else receiver_headers
        other_headers = receiver_headers if i % 2 == 0 else sender_headers
        await client.post(f"/api/v1/games/penalty/matches/{match_id}/pick", headers=kicker_headers, json={"zone": "top_left"})
        await client.post(f"/api/v1/games/penalty/matches/{match_id}/pick", headers=other_headers, json={"zone": "top_left"})

    await db_session.refresh(sender)
    await db_session.refresh(receiver)
    assert sender.balance == balance_before
    assert receiver.balance == 500


async def test_penalty_pvp_kick_timeout_auto_resolves(client, db_session, bot_token):
    from datetime import datetime, timedelta, timezone

    from app.models.penalty import PenaltyMatch

    match_id, sender, receiver, sender_headers, receiver_headers = await _create_and_accept(
        client, db_session, bot_token, 860205, 860206
    )

    # sender (kicker) picks; receiver never does — force the kick_deadline
    # into the past to simulate the 10s window elapsing.
    await client.post(f"/api/v1/games/penalty/matches/{match_id}/pick", headers=sender_headers, json={"zone": "top_left"})
    match = await db_session.get(PenaltyMatch, match_id)
    state = dict(match.server_state)
    state["kick_deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    match.server_state = state
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(match, "server_state")
    db_session.add(match)
    await db_session.commit()

    resp = await client.get(f"/api/v1/games/penalty/matches/{match_id}", headers=sender_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rounds"]) == 1  # the round resolved despite receiver never picking


async def test_penalty_pvp_match_timeout_ends_in_current_score(client, db_session, bot_token):
    from datetime import datetime, timedelta, timezone

    from app.models.penalty import PenaltyMatch

    match_id, sender, receiver, sender_headers, receiver_headers = await _create_and_accept(
        client, db_session, bot_token, 860207, 860208
    )

    # One kick resolved in the sender's favor, then force match_deadline
    # into the past — the match must end right there, sender ahead 1:0.
    await client.post(f"/api/v1/games/penalty/matches/{match_id}/pick", headers=sender_headers, json={"zone": "top_left"})
    await client.post(f"/api/v1/games/penalty/matches/{match_id}/pick", headers=receiver_headers, json={"zone": "bottom_right"})

    match = await db_session.get(PenaltyMatch, match_id)
    state = dict(match.server_state)
    state["match_deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    match.server_state = state
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(match, "server_state")
    db_session.add(match)
    await db_session.commit()

    resp = await client.get(f"/api/v1/games/penalty/matches/{match_id}", headers=sender_headers)
    body = resp.json()
    assert body["status"] == "finished"
    assert body["result"] == "win"
    assert body["user_score"] == 1 and body["opponent_score"] == 0
