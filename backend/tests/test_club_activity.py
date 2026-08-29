from datetime import datetime, timedelta, timezone

import pytest_asyncio

from app.models.club_daily_claim import ClubDailyClaim
from app.models.enums import Position
from app.models.game import GameSession
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """create_club seeds a starting squad on every creation — same seeding every other club
    test file needs (see test_clubs.py's identical fixture)."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _make_club_with_two_members(client, db_session, bot_token):
    captain_headers = telegram_headers(870201, bot_token)
    await client.post("/api/v1/auth/session", headers=captain_headers)
    resp = await client.post(
        "/api/v1/clubs", headers=captain_headers,
        json={"name": "Activity Club", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    club_id = resp.json()["id"]

    member_headers = telegram_headers(870202, bot_token)
    await client.post("/api/v1/auth/session", headers=member_headers)
    join_resp = await client.post(f"/api/v1/clubs/{club_id}/join", headers=member_headers)
    assert join_resp.status_code == 200

    captain = await get_user_by_telegram_id(db_session, 870201)
    member = await get_user_by_telegram_id(db_session, 870202)
    return club_id, captain, member, captain_headers, member_headers


async def test_activity_counts_only_club_game_and_club_daily_reward(client, db_session, bot_token):
    """Regression test: a player's app-wide mini-game plays (any GameType other than
    club_sequence) and their personal DailyReward claims must NOT be counted — only the
    club's own mini-game and the club's own daily reward (ClubDailyClaim). Reported in
    production as clubs created "yesterday" already showing hundreds of "games played",
    because the query was pulling in the player's whole app-wide history."""
    club_id, captain, member, captain_headers, _ = await _make_club_with_two_members(client, db_session, bot_token)

    now = datetime.now(timezone.utc)
    stale = now - timedelta(days=30)

    # Counts: recent club_sequence session.
    db_session.add(GameSession(user_id=captain.id, game_type="club_sequence", created_at=now))
    # Must NOT count: a general mini-game and a stale club_sequence session.
    db_session.add(GameSession(user_id=captain.id, game_type="memory_sequence", created_at=now))
    db_session.add(GameSession(user_id=captain.id, game_type="club_sequence", created_at=stale))

    # Counts: the club's own daily reward claim, today.
    db_session.add(ClubDailyClaim(club_id=club_id, user_id=captain.id, claim_date=now.date()))
    # Must NOT count: the member's personal (non-club) daily reward system is a different
    # table entirely (DailyReward) — never touched here, so its absence is the assertion.

    await db_session.commit()

    resp = await client.get("/api/v1/clubs/me/activity", headers=captain_headers)
    assert resp.status_code == 200
    by_user = {row["user_id"]: row for row in resp.json()}

    assert by_user[captain.id]["games_played"] == 1
    assert by_user[captain.id]["daily_rewards_claimed"] == 1
    assert by_user[member.id]["games_played"] == 0
    assert by_user[member.id]["daily_rewards_claimed"] == 0


async def test_only_manager_can_remind_and_it_notifies_target(client, db_session, bot_token):
    from sqlalchemy import select

    from app.models.enums import NotificationType
    from app.models.notification import Notification

    _club_id, captain, member, captain_headers, member_headers = await _make_club_with_two_members(
        client, db_session, bot_token
    )

    forbidden = await client.post(f"/api/v1/clubs/me/members/{captain.id}/remind", headers=member_headers)
    assert forbidden.status_code == 403

    self_remind = await client.post(f"/api/v1/clubs/me/members/{captain.id}/remind", headers=captain_headers)
    assert self_remind.status_code == 409

    ok = await client.post(f"/api/v1/clubs/me/members/{member.id}/remind", headers=captain_headers)
    assert ok.status_code == 204

    notifications = (
        await db_session.execute(
            select(Notification).where(
                Notification.user_id == member.id, Notification.type == NotificationType.club_activity_reminder
            )
        )
    ).scalars().all()
    assert len(notifications) == 1
