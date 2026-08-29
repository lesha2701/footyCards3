from datetime import datetime, timedelta, timezone

import pytest_asyncio

from app.models.daily_reward import DailyReward
from app.models.enums import Position
from app.models.game import GameSession
from app.models.match import Match
from app.models.penalty import PenaltyMatch
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

    member_headers = telegram_headers(870202, bot_token)
    await client.post("/api/v1/auth/session", headers=member_headers)
    join_resp = await client.post(f"/api/v1/clubs/{resp.json()['id']}/join", headers=member_headers)
    assert join_resp.status_code == 200

    captain = await get_user_by_telegram_id(db_session, 870201)
    member = await get_user_by_telegram_id(db_session, 870202)
    return captain, member, captain_headers, member_headers


async def test_activity_counts_games_and_rewards_within_window(client, db_session, bot_token):
    captain, member, captain_headers, _ = await _make_club_with_two_members(client, db_session, bot_token)

    now = datetime.now(timezone.utc)
    stale = now - timedelta(days=30)

    # Two recent single-player game sessions for the captain, one stale one that shouldn't count.
    db_session.add(GameSession(user_id=captain.id, game_type="memory_sequence", created_at=now))
    db_session.add(GameSession(user_id=captain.id, game_type="saboteur", created_at=now))
    db_session.add(GameSession(user_id=captain.id, game_type="memory_sequence", created_at=stale))

    # A friend match where the member is the opponent (not the initiator) — must still count for the member.
    db_session.add(
        Match(
            user_id=captain.id, opponent_user_id=member.id, opponent_name="Member", difficulty="medium",
            user_team_strength=100, opponent_team_strength=100, user_score=1, opponent_score=0, created_at=now,
        )
    )
    db_session.add(PenaltyMatch(user_id=member.id, opponent_name="Bot", created_at=now))

    db_session.add(DailyReward(user_id=captain.id, reward_date=now.date(), streak_day=1, coins_awarded=50, created_at=now))
    await db_session.commit()

    resp = await client.get("/api/v1/clubs/me/activity", headers=captain_headers)
    assert resp.status_code == 200
    by_user = {row["user_id"]: row for row in resp.json()}

    assert by_user[captain.id]["games_played"] == 3  # 2 recent GameSessions + 1 Match as initiator
    assert by_user[captain.id]["daily_rewards_claimed"] == 1
    assert by_user[member.id]["games_played"] == 2  # Match as opponent + own PenaltyMatch
    assert by_user[member.id]["daily_rewards_claimed"] == 0


async def test_only_manager_can_remind_and_it_notifies_target(client, db_session, bot_token):
    from sqlalchemy import select

    from app.models.enums import NotificationType
    from app.models.notification import Notification

    captain, member, captain_headers, member_headers = await _make_club_with_two_members(client, db_session, bot_token)

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
