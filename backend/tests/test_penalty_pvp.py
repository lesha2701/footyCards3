import pytest

import app.core.rate_limit as rate_limit_module
from app.models.card import UserCard
from app.models.enums import CardSource, Rarity
from app.services import penalty_service
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


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
    sender.penalty_rating = 5
    receiver.penalty_rating = 5
    db_session.add_all([sender, receiver])
    await db_session.commit()

    # Regulation is 10 kicks (5 as each side's kicker). Both shooters always
    # aim "top_left"; the defender's dive zone is chosen to mismatch (goal)
    # on the sender's kicks and match (saved) on the receiver's — this
    # guarantees the sender finishes strictly ahead without ever needing a
    # tied score, so the match ends at regulation without sudden death, and
    # exercises the win/+3/-1 rating-delta path (the draw/+1 path is covered
    # separately by test_penalty_pvp_match_timeout_draw_when_tied, which
    # forces a genuine tie via the match clock).
    for i in range(10):
        kicker_headers = sender_headers if i % 2 == 0 else receiver_headers
        other_headers = receiver_headers if i % 2 == 0 else sender_headers
        dive_zone = "top_right" if i % 2 == 0 else "top_left"  # mismatch for sender's kicks, match for receiver's
        r1 = await client.post(
            f"/api/v1/games/penalty/matches/{match_id}/pick", headers=kicker_headers, json={"zone": "top_left"}
        )
        assert r1.status_code == 200
        r2 = await client.post(
            f"/api/v1/games/penalty/matches/{match_id}/pick", headers=other_headers, json={"zone": dive_zone}
        )
        assert r2.status_code == 200

    final = r2.json()
    assert final["status"] == "finished"
    assert final["result"] == "win"
    assert final["user_score"] > 0 and final["opponent_score"] == 0

    await db_session.refresh(sender)
    await db_session.refresh(receiver)
    assert sender.penalty_rating == 8  # 5 + 3 (win)
    assert receiver.penalty_rating == 4  # 5 - 1 (loss)


async def test_penalty_pvp_gives_no_coins(client, db_session, bot_token):
    match_id, sender, receiver, sender_headers, receiver_headers = await _create_and_accept(
        client, db_session, bot_token, 860203, 860204
    )
    balance_before = sender.balance

    # Same mismatch-vs-match pattern as the full-match test above, so the
    # sender finishes ahead and the match ends at regulation.
    for i in range(10):
        kicker_headers = sender_headers if i % 2 == 0 else receiver_headers
        other_headers = receiver_headers if i % 2 == 0 else sender_headers
        dive_zone = "top_right" if i % 2 == 0 else "top_left"
        await client.post(f"/api/v1/games/penalty/matches/{match_id}/pick", headers=kicker_headers, json={"zone": "top_left"})
        await client.post(f"/api/v1/games/penalty/matches/{match_id}/pick", headers=other_headers, json={"zone": dive_zone})

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


async def test_penalty_pvp_match_timeout_ends_in_current_score(client, db_session, bot_token, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.models.penalty import PenaltyMatch

    match_id, sender, receiver, sender_headers, receiver_headers = await _create_and_accept(
        client, db_session, bot_token, 860207, 860208
    )
    # A single kick, so the shooter's own ~5% miss-chance floor (at rating
    # 99) isn't negligible here the way it is in the 5-kick tests above —
    # force it to zero so this test isn't flaky.
    monkeypatch.setattr(penalty_service, "player_miss_chance", lambda rating: 0.0)

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


async def test_penalty_pvp_match_timeout_draw_when_tied(client, db_session, bot_token):
    """The match clock is the only way a PvP match ends in a draw (regulation
    ties continue into sudden death instead) — force a still-tied score at
    timeout and confirm _finish_match's MatchResult.draw branch (+1/+1).
    Like the other two timeout tests above, this reaches the sweep logic
    through GET /games/penalty/matches/{id}, so it 404s (expected) until
    Task 5's get_match (which calls _auto_resolve_overdue) exists."""
    from datetime import datetime, timedelta, timezone

    from app.models.penalty import PenaltyMatch
    from sqlalchemy.orm.attributes import flag_modified

    match_id, sender, receiver, sender_headers, receiver_headers = await _create_and_accept(
        client, db_session, bot_token, 860209, 860210
    )
    sender.penalty_rating = 5
    receiver.penalty_rating = 5
    db_session.add_all([sender, receiver])
    await db_session.commit()

    # Both sides always dive the same zone they shoot — every kick is
    # saved, score stays 0:0 — then the match clock (not regulation) is
    # what ends it.
    await client.post(f"/api/v1/games/penalty/matches/{match_id}/pick", headers=sender_headers, json={"zone": "top_left"})
    await client.post(f"/api/v1/games/penalty/matches/{match_id}/pick", headers=receiver_headers, json={"zone": "top_left"})

    match = await db_session.get(PenaltyMatch, match_id)
    state = dict(match.server_state)
    state["match_deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    match.server_state = state
    flag_modified(match, "server_state")
    db_session.add(match)
    await db_session.commit()

    resp = await client.get(f"/api/v1/games/penalty/matches/{match_id}", headers=sender_headers)
    body = resp.json()
    assert body["status"] == "finished"
    assert body["result"] == "draw"
    assert body["user_score"] == 0 and body["opponent_score"] == 0

    await db_session.refresh(sender)
    await db_session.refresh(receiver)
    assert sender.penalty_rating == 6  # 5 + 1 (draw)
    assert receiver.penalty_rating == 6  # 5 + 1 (draw)


async def test_penalty_pvp_forfeit_counts_as_a_loss_for_the_forfeiter(client, db_session, bot_token):
    """Leaving mid-match (confirmed via the frontend's leave dialog) must
    cost the forfeiter -1 and the opponent +3, regardless of the partial
    score — same rule Tactico's forfeit_match enforces."""
    match_id, sender, receiver, sender_headers, receiver_headers = await _create_and_accept(
        client, db_session, bot_token, 860211, 860212
    )
    sender.penalty_rating = 5
    receiver.penalty_rating = 5
    db_session.add_all([sender, receiver])
    await db_session.commit()

    # Sender is ahead 1:0 when they forfeit — must still count as a loss
    # for them, not a win just because they were winning on the scoreboard.
    await client.post(f"/api/v1/games/penalty/matches/{match_id}/pick", headers=sender_headers, json={"zone": "top_left"})
    await client.post(f"/api/v1/games/penalty/matches/{match_id}/pick", headers=receiver_headers, json={"zone": "bottom_right"})

    resp = await client.post(f"/api/v1/games/penalty/matches/{match_id}/forfeit", headers=sender_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "finished"
    assert body["result"] == "loss"
    assert body["rating_delta"] == -1

    await db_session.refresh(sender)
    await db_session.refresh(receiver)
    assert sender.penalty_rating == 4  # 5 - 1
    assert receiver.penalty_rating == 8  # 5 + 3

    # No coins for PvP, ever — not even via forfeit.
    assert receiver.balance == 500


async def test_penalty_pvp_forfeit_by_opponent_counts_as_win_for_challenger(client, db_session, bot_token):
    match_id, sender, receiver, sender_headers, receiver_headers = await _create_and_accept(
        client, db_session, bot_token, 860213, 860214
    )

    resp = await client.post(f"/api/v1/games/penalty/matches/{match_id}/forfeit", headers=receiver_headers)
    assert resp.status_code == 200
    body = resp.json()
    # Hydrated for the forfeiting receiver's own view ("opponent" storage
    # side) — they see their own loss, not the challenger's win.
    assert body["result"] == "loss"
    assert body["rating_delta"] == -1

    await db_session.refresh(sender)
    await db_session.refresh(receiver)
    assert sender.penalty_rating == 3  # 0 + 3 (win, as the non-forfeiting challenger)
    assert receiver.penalty_rating == 0  # 0 - 1 clamped at the floor


async def test_penalty_pvp_forfeit_rejects_non_participant(client, db_session, bot_token):
    match_id, sender, receiver, sender_headers, receiver_headers = await _create_and_accept(
        client, db_session, bot_token, 860215, 860216
    )
    stranger = await _register(client, db_session, 860217, bot_token)
    stranger_headers = telegram_headers(860217, bot_token)

    resp = await client.post(f"/api/v1/games/penalty/matches/{match_id}/forfeit", headers=stranger_headers)
    assert resp.status_code == 403


async def test_penalty_pvp_forfeit_rejects_already_finished_match(client, db_session, bot_token):
    match_id, sender, receiver, sender_headers, receiver_headers = await _create_and_accept(
        client, db_session, bot_token, 860218, 860219
    )

    first = await client.post(f"/api/v1/games/penalty/matches/{match_id}/forfeit", headers=sender_headers)
    assert first.status_code == 200

    second = await client.post(f"/api/v1/games/penalty/matches/{match_id}/forfeit", headers=sender_headers)
    assert second.status_code == 409
