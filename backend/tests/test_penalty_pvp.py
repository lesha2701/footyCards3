import pytest
from sqlalchemy import select

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


async def test_penalty_pvp_friend_match_resolves_with_score_but_no_rating(client, db_session, bot_token):
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
    assert sender.penalty_rating == 5  # unchanged — friend matches no longer touch rating
    assert receiver.penalty_rating == 5  # unchanged — friend matches no longer touch rating


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
    assert sender.penalty_rating == 5  # unchanged — friend matches no longer touch rating
    assert receiver.penalty_rating == 5  # unchanged — friend matches no longer touch rating


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
    assert body["rating_delta"] == 0

    await db_session.refresh(sender)
    await db_session.refresh(receiver)
    assert sender.penalty_rating == 5  # unchanged — friend matches no longer touch rating
    assert receiver.penalty_rating == 5  # unchanged — friend matches no longer touch rating

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
    assert body["rating_delta"] == 0

    await db_session.refresh(sender)
    await db_session.refresh(receiver)
    assert sender.penalty_rating == 0  # unchanged — friend matches no longer touch rating
    assert receiver.penalty_rating == 0  # unchanged — friend matches no longer touch rating


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


from app.models.enums import PenaltyOpponentType
from app.models.penalty import PenaltyQueueEntry


async def test_penalty_opponent_type_has_friend_and_online():
    assert PenaltyOpponentType.friend == "friend"
    assert PenaltyOpponentType.online == "online"


async def test_existing_penalty_match_defaults_opponent_type_to_friend(client, db_session, bot_token):
    sender = await _register(client, db_session, 861001, bot_token)
    receiver = await _register(client, db_session, 861002, bot_token)
    sender_card = await _grant_card(db_session, sender.id)

    resp = await client.post(
        "/api/v1/games/penalty/challenges", headers=telegram_headers(861001, bot_token),
        json={"opponent_user_id": receiver.id, "user_card_id": sender_card.id},
    )
    assert resp.status_code == 200
    assert resp.json()["opponent_type"] == "friend"


async def test_penalty_queue_entry_roundtrip(client, db_session, bot_token):
    user = await _register(client, db_session, 861003, bot_token)
    card = await _grant_card(db_session, user.id)

    entry = PenaltyQueueEntry(user_id=user.id, user_card_id=card.id)
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)

    assert entry.id is not None
    assert entry.matched_match_id is None


async def test_penalty_start_search_requires_owned_card(client, db_session, bot_token):
    sender = await _register(client, db_session, 862001, bot_token)
    other_owner = await _register(client, db_session, 862002, bot_token)
    someone_elses_card = await _grant_card(db_session, other_owner.id)

    resp = await client.post(
        "/api/v1/games/penalty/matchmaking/search", headers=telegram_headers(862001, bot_token),
        json={"user_card_id": someone_elses_card.id},
    )
    assert resp.status_code == 403


async def test_penalty_start_search_rejects_second_entry(client, db_session, bot_token):
    user = await _register(client, db_session, 862003, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(862003, bot_token)

    first = await client.post(
        "/api/v1/games/penalty/matchmaking/search", headers=headers, json={"user_card_id": card.id}
    )
    assert first.status_code == 200
    second = await client.post(
        "/api/v1/games/penalty/matchmaking/search", headers=headers, json={"user_card_id": card.id}
    )
    assert second.status_code == 409
    assert "уже ищешь" in second.json()["error"]["message"]


async def test_penalty_two_waiting_players_get_paired(client, db_session, bot_token):
    user_a = await _register(client, db_session, 862004, bot_token)
    card_a = await _grant_card(db_session, user_a.id)
    user_b = await _register(client, db_session, 862005, bot_token)
    card_b = await _grant_card(db_session, user_b.id)
    headers_a = telegram_headers(862004, bot_token)
    headers_b = telegram_headers(862005, bot_token)

    await client.post("/api/v1/games/penalty/matchmaking/search", headers=headers_a, json={"user_card_id": card_a.id})
    await client.post("/api/v1/games/penalty/matchmaking/search", headers=headers_b, json={"user_card_id": card_b.id})

    status_a = await client.get("/api/v1/games/penalty/matchmaking/status", headers=headers_a)
    assert status_a.json()["status"] == "matched"
    match_id = status_a.json()["match_id"]

    status_b = await client.get("/api/v1/games/penalty/matchmaking/status", headers=headers_b)
    assert status_b.json()["match_id"] == match_id

    match_resp = await client.get(f"/api/v1/games/penalty/matches/{match_id}", headers=headers_a)
    body = match_resp.json()
    assert body["opponent_type"] == "online"
    assert body["status"] == "in_progress"
    assert body["kick_deadline"] is not None
    assert body["match_deadline"] is not None


async def test_penalty_search_timeout(client, db_session, bot_token):
    from datetime import datetime, timedelta, timezone

    user = await _register(client, db_session, 862006, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(862006, bot_token)
    await client.post("/api/v1/games/penalty/matchmaking/search", headers=headers, json={"user_card_id": card.id})

    entry = (
        await db_session.execute(select(PenaltyQueueEntry).where(PenaltyQueueEntry.user_id == user.id))
    ).scalar_one()
    entry.created_at = datetime.now(timezone.utc) - timedelta(seconds=61)
    db_session.add(entry)
    await db_session.commit()

    resp = await client.get("/api/v1/games/penalty/matchmaking/status", headers=headers)
    assert resp.json()["status"] == "timeout"


async def test_penalty_pairing_skips_entry_whose_card_was_traded_away(client, db_session, bot_token):
    user_a = await _register(client, db_session, 862007, bot_token)
    card_a = await _grant_card(db_session, user_a.id)
    user_b = await _register(client, db_session, 862008, bot_token)
    card_b = await _grant_card(db_session, user_b.id)
    headers_a = telegram_headers(862007, bot_token)
    headers_b = telegram_headers(862008, bot_token)

    await client.post("/api/v1/games/penalty/matchmaking/search", headers=headers_a, json={"user_card_id": card_a.id})
    await client.post("/api/v1/games/penalty/matchmaking/search", headers=headers_b, json={"user_card_id": card_b.id})

    # Simulate card_b changing hands (e.g. via a trade) while both wait in the queue.
    card_b.owner_id = user_a.id
    db_session.add(card_b)
    await db_session.commit()

    status_a = await client.get("/api/v1/games/penalty/matchmaking/status", headers=headers_a)
    assert status_a.json()["status"] == "searching"  # B's stale entry dropped, not a broken match


async def test_penalty_cancel_search(client, db_session, bot_token):
    user = await _register(client, db_session, 862009, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(862009, bot_token)
    await client.post("/api/v1/games/penalty/matchmaking/search", headers=headers, json={"user_card_id": card.id})

    resp = await client.post("/api/v1/games/penalty/matchmaking/cancel", headers=headers)
    assert resp.status_code == 204
    status = await client.get("/api/v1/games/penalty/matchmaking/status", headers=headers)
    assert status.json()["status"] == "not_searching"


async def test_penalty_matched_player_can_search_again_after_row_cleanup(client, db_session, bot_token):
    """Regression test for a queue-entry leak: get_search_status used to set
    matched_match_id on both sides' PenaltyQueueEntry rows without ever
    deleting either one. start_search's "already searching" check doesn't
    distinguish matched from unmatched rows, so before the fix, *any* player
    who had ever been matched once would hit a permanent 409 "уже ищешь" on
    every future search attempt — matchmaking was effectively a one-time
    feature per player. Covers both cleanup paths: the pairing caller (A),
    whose row is deleted immediately when their own poll creates the match,
    and the candidate (B), whose row is deleted the first time *their* own
    poll observes the already-set matched_match_id."""
    user_a = await _register(client, db_session, 862010, bot_token)
    card_a = await _grant_card(db_session, user_a.id)
    user_b = await _register(client, db_session, 862011, bot_token)
    card_b = await _grant_card(db_session, user_b.id)
    headers_a = telegram_headers(862010, bot_token)
    headers_b = telegram_headers(862011, bot_token)

    await client.post("/api/v1/games/penalty/matchmaking/search", headers=headers_a, json={"user_card_id": card_a.id})
    await client.post("/api/v1/games/penalty/matchmaking/search", headers=headers_b, json={"user_card_id": card_b.id})

    # A is the pairing caller: their poll both discovers and (per the fix)
    # deletes their own queue row.
    status_a = await client.get("/api/v1/games/penalty/matchmaking/status", headers=headers_a)
    assert status_a.json()["status"] == "matched"
    match_id = status_a.json()["match_id"]

    # B is the candidate: this is B's own first poll, so it still correctly
    # reports the match (both sides still learn about it, matching
    # pre-fix behavior) — and, per the fix, cleans up B's row now too.
    status_b = await client.get("/api/v1/games/penalty/matchmaking/status", headers=headers_b)
    assert status_b.json()["status"] == "matched"
    assert status_b.json()["match_id"] == match_id

    no_queue_rows_left = (
        await db_session.execute(select(PenaltyQueueEntry).where(PenaltyQueueEntry.user_id.in_([user_a.id, user_b.id])))
    ).scalars().all()
    assert no_queue_rows_left == []

    # Resolve the match so the *separate*, correct "you have an active
    # match" guard in start_search doesn't mask the bug this test targets.
    forfeit = await client.post(f"/api/v1/games/penalty/matches/{match_id}/forfeit", headers=headers_a)
    assert forfeit.status_code == 200

    new_card_a = await _grant_card(db_session, user_a.id)
    resp_a = await client.post(
        "/api/v1/games/penalty/matchmaking/search", headers=headers_a, json={"user_card_id": new_card_a.id}
    )
    assert resp_a.status_code == 200  # would incorrectly 409 "уже ищешь" before the fix

    new_card_b = await _grant_card(db_session, user_b.id)
    resp_b = await client.post(
        "/api/v1/games/penalty/matchmaking/search", headers=headers_b, json={"user_card_id": new_card_b.id}
    )
    assert resp_b.status_code == 200  # same fix, exercised via the candidate's cleanup path


# ---------------------------------------------------------------------------
# Matchmaking — final whole-branch review fix wave (Critical Fixes 1 & 2, and
# the hourly-limit-at-search-time part of Important Fix 4). Mirrors
# test_tactico.py's equivalent tests identically in shape.
# ---------------------------------------------------------------------------

async def _set_config(db_session, **overrides) -> None:
    from app.models.game_config import GameConfig

    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    for key, value in overrides.items():
        setattr(config, key, value)
    await db_session.commit()


async def test_penalty_stale_queue_entry_is_never_selected_as_pairing_candidate(client, db_session, bot_token):
    """Regression for Critical Fix 2: the candidate query used to have no
    created_at cutoff, and ORDER BY created_at picked the OLDEST entry —
    exactly the one most likely to be an abandoned ghost. A live searcher
    must not get paired with a queue entry older than
    MATCHMAKING_TIMEOUT_SECONDS, and that ghost entry must be left alone
    (only the caller's own row is ever touched by get_search_status)."""
    from datetime import datetime, timedelta, timezone

    user_a = await _register(client, db_session, 862020, bot_token)
    card_a = await _grant_card(db_session, user_a.id)
    headers_a = telegram_headers(862020, bot_token)

    ghost_user = await _register(client, db_session, 862021, bot_token)
    ghost_card = await _grant_card(db_session, ghost_user.id)
    ghost_entry = PenaltyQueueEntry(
        user_id=ghost_user.id, user_card_id=ghost_card.id,
        created_at=datetime.now(timezone.utc) - timedelta(hours=3),
    )
    db_session.add(ghost_entry)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/games/penalty/matchmaking/search", headers=headers_a, json={"user_card_id": card_a.id}
    )
    assert resp.status_code == 200

    status_a = await client.get("/api/v1/games/penalty/matchmaking/status", headers=headers_a)
    assert status_a.json()["status"] == "searching"  # not paired with the 3h-old ghost

    remaining = (
        await db_session.execute(select(PenaltyQueueEntry).where(PenaltyQueueEntry.user_id == ghost_user.id))
    ).scalar_one_or_none()
    assert remaining is not None and remaining.id == ghost_entry.id  # untouched


async def test_penalty_search_reclaims_own_entry_stale_past_timeout(client, db_session, bot_token):
    """Regression for Critical Fix 1: start_search used to raise 409 on ANY
    pre-existing queue row unconditionally, permanently locking out a player
    whose client stopped polling while a row existed. A row aged past
    MATCHMAKING_TIMEOUT_SECONDS must now be reclaimed instead."""
    from datetime import datetime, timedelta, timezone

    user = await _register(client, db_session, 862022, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(862022, bot_token)

    stale_created_at = datetime.now(timezone.utc) - timedelta(seconds=61)
    stale_entry = PenaltyQueueEntry(user_id=user.id, user_card_id=card.id, created_at=stale_created_at)
    db_session.add(stale_entry)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/games/penalty/matchmaking/search", headers=headers, json={"user_card_id": card.id}
    )
    assert resp.status_code == 200  # would incorrectly 409 "уже ищешь" before the fix

    # The search API call ran in its own DB session (see conftest's
    # _override_get_db); this session's identity map may still hold the
    # pre-reclaim in-memory object under the same primary key (SQLite
    # readily reuses rowids on a near-empty table), which would otherwise
    # mask the fresh row's data. Expire so the next query re-reads from DB.
    entries = (
        await db_session.execute(
            select(PenaltyQueueEntry).where(PenaltyQueueEntry.user_id == user.id)
            .execution_options(populate_existing=True)
        )
    ).scalars().all()
    assert len(entries) == 1
    from app.core.timeutil import ensure_aware

    assert ensure_aware(entries[0].created_at) > stale_created_at  # a genuinely fresh row, not the stale one


async def test_penalty_search_reclaims_own_entry_already_matched(client, db_session, bot_token):
    """Regression for Critical Fix 1's second reclaim branch: a queue row
    with matched_match_id already set (the player got matched via someone
    else's poll but never checked back) must also be reclaimable — not just
    time-expired rows."""
    user = await _register(client, db_session, 862023, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(862023, bot_token)

    other_user = await _register(client, db_session, 862024, bot_token)
    other_card = await _grant_card(db_session, other_user.id)
    other_receiver = await _register(client, db_session, 862025, bot_token)
    other_receiver_card = await _grant_card(db_session, other_receiver.id)
    challenge = await client.post(
        "/api/v1/games/penalty/challenges", headers=telegram_headers(862024, bot_token),
        json={"opponent_user_id": other_receiver.id, "user_card_id": other_card.id},
    )
    match_id = challenge.json()["id"]

    matched_entry = PenaltyQueueEntry(user_id=user.id, user_card_id=card.id, matched_match_id=match_id)
    db_session.add(matched_entry)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/games/penalty/matchmaking/search", headers=headers, json={"user_card_id": card.id}
    )
    assert resp.status_code == 200  # would incorrectly 409 "уже ищешь" before the fix

    entries = (
        await db_session.execute(
            select(PenaltyQueueEntry).where(PenaltyQueueEntry.user_id == user.id)
            .execution_options(populate_existing=True)
        )
    ).scalars().all()
    assert len(entries) == 1
    assert entries[0].matched_match_id is None


async def test_penalty_search_rejects_when_hourly_limit_already_reached(client, db_session, bot_token):
    """Regression for Important Fix 4: the hourly limit must be checked as a
    precondition at start_search time (non-consuming), not only at pairing
    time — a player already over the limit must not be allowed to join the
    queue and burn the full 60s wait for nothing."""
    from datetime import datetime, timezone

    user = await _register(client, db_session, 862026, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(862026, bot_token)
    await _set_config(db_session, hourly_game_limit=1)
    user.penalty_hourly_attempts = 1
    user.penalty_hour_started_at = datetime.now(timezone.utc)
    db_session.add(user)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/games/penalty/matchmaking/search", headers=headers, json={"user_card_id": card.id}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["hourly_limit"] == 1

    entries = (
        await db_session.execute(select(PenaltyQueueEntry).where(PenaltyQueueEntry.user_id == user.id))
    ).scalars().all()
    assert entries == []  # the check must not have created a queue row before rejecting


async def test_penalty_online_win_doubles_rating(client, db_session, bot_token):
    user_a = await _register(client, db_session, 862010, bot_token)
    card_a = await _grant_card(db_session, user_a.id, rating=99)
    user_b = await _register(client, db_session, 862011, bot_token)
    card_b = await _grant_card(db_session, user_b.id, rating=1)
    headers_a = telegram_headers(862010, bot_token)
    headers_b = telegram_headers(862011, bot_token)

    user_a.penalty_rating = 5
    user_b.penalty_rating = 5
    db_session.add_all([user_a, user_b])
    await db_session.commit()

    await client.post("/api/v1/games/penalty/matchmaking/search", headers=headers_a, json={"user_card_id": card_a.id})
    await client.post("/api/v1/games/penalty/matchmaking/search", headers=headers_b, json={"user_card_id": card_b.id})
    status_a = await client.get("/api/v1/games/penalty/matchmaking/status", headers=headers_a)
    match_id = status_a.json()["match_id"]

    for i in range(10):
        kicker_headers = headers_a if i % 2 == 0 else headers_b
        other_headers = headers_b if i % 2 == 0 else headers_a
        dive_zone = "top_right" if i % 2 == 0 else "top_left"
        await client.post(
            f"/api/v1/games/penalty/matches/{match_id}/pick", headers=kicker_headers, json={"zone": "top_left"}
        )
        resp = await client.post(
            f"/api/v1/games/penalty/matches/{match_id}/pick", headers=other_headers, json={"zone": dive_zone}
        )

    final = resp.json()
    assert final["status"] == "finished"

    await db_session.refresh(user_a)
    await db_session.refresh(user_b)
    # win/loss doubled: +6/-2 instead of +3/-1 (or +2/+2 instead of +1/+1 on
    # a draw) — either way the combined total moves by 4, not 2
    assert (user_a.penalty_rating + user_b.penalty_rating) - 10 == 4


async def test_penalty_bot_win_triggers_league_reward(client, db_session, bot_token):
    from app.models.league import LeagueTier

    tier = LeagueTier(name="Дворовая лига", min_rating=0, reward_coins=10, sort_order=0)
    db_session.add(tier)
    await db_session.commit()

    headers = telegram_headers(862012, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 862012)
    card = await _grant_card(db_session, user.id, rating=99)

    resp = await client.post("/api/v1/games/penalty/start", headers=headers, json={"user_card_id": card.id})
    session_id = resp.json()["session_id"]

    body = resp.json()
    while not body.get("is_finished"):
        body = (
            await client.post(
                f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": "top_left"}
            )
        ).json()

    if body["result"] == "win":
        notifications = (await client.get("/api/v1/notifications", headers=headers)).json()
        assert any(n["type"] == "league_promoted" for n in notifications)
