"""Clubs stay fair: no reward for a mercenary or a passenger, a pause after
leaving, lost games worth less, and a club outlives a vanished captain."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.config import get_settings
from app.core.timeutil import local_today
from app.models.club import Club, ClubMember
from app.models.club_reward import ClubRewardGrant
from app.models.enums import ClubRole, GameSessionStatus, MatchResult, NotificationType, PenaltyMatchStatus, Position
from app.models.game import GameSession
from app.models.notification import Notification
from app.models.penalty import PenaltyMatch
from app.models.user import User
from app.services import club_league_service, club_reward_service, club_service, club_war_service
from app.services.club_league_service import _activity, _Tally, game_points, week_start_for
from app.services.game_config_service import get_config
from app.services.reward_bundle_service import Bundle
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

INTERNAL = {"X-Internal-Secret": get_settings().internal_api_secret}
NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


@pytest.fixture(autouse=True)
async def _seed(db_session):
    rate_limit_module._hits.clear()
    for position in (Position.GK, Position.GK, Position.LB, Position.LB, Position.CB, Position.CB, Position.RB,
                     Position.RB, Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM, Position.LW,
                     Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)
    club_league_service._table_cache.clear()


async def _user(client, db_session, bot_token, telegram_id):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    return (await get_user_by_telegram_id(db_session, telegram_id)).id, headers


async def _club(client, db_session, bot_token, telegram_id, name):
    user_id, headers = await _user(client, db_session, bot_token, telegram_id)
    club_id = (await client.post("/api/v1/clubs", headers=headers, json={
        "name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000",
    })).json()["id"]
    return club_id, user_id, headers


async def _age_membership(db_session, user_id, hours):
    member = (await db_session.execute(select(ClubMember).where(ClubMember.user_id == user_id))).scalar_one()
    member.joined_at = NOW() - timedelta(hours=hours)
    await db_session.commit()


async def test_leaving_a_club_pauses_joining_another_but_a_kick_does_not(client, db_session, bot_token):
    club_a, _cap, headers_cap = await _club(client, db_session, bot_token, 941001, "Пауза А")
    club_b, _other, _ = await _club(client, db_session, bot_token, 941002, "Пауза Б")
    user_id, headers = await _user(client, db_session, bot_token, 941003)

    assert (await client.post(f"/api/v1/clubs/{club_a}/join", headers=headers)).status_code == 200
    assert (await client.post(f"/api/v1/clubs/me/members/{user_id}/kick", headers=headers_cap)).status_code == 200
    # Kicked: free to go elsewhere at once.
    assert (await client.post(f"/api/v1/clubs/{club_a}/join", headers=headers)).status_code == 200

    assert (await client.post("/api/v1/clubs/me/leave", headers=headers)).status_code in (200, 204)
    blocked = await client.post(f"/api/v1/clubs/{club_b}/join", headers=headers)
    assert blocked.status_code == 409 and "24 ч" in blocked.json()["error"]["message"]

    user = await db_session.get(User, user_id)
    user.club_left_at = NOW() - timedelta(hours=25)
    await db_session.commit()
    assert (await client.post(f"/api/v1/clubs/{club_b}/join", headers=headers)).status_code == 200


async def test_mercenary_gets_no_quest_or_war_reward_but_shop_still_pays(client, db_session, bot_token):
    club_id, captain_id, headers_cap = await _club(client, db_session, bot_token, 942001, "Стаж")
    await _age_membership(db_session, captain_id, 48)
    newcomer_id, headers_new = await _user(client, db_session, bot_token, 942002)
    assert (await client.post(f"/api/v1/clubs/{club_id}/join", headers=headers_new)).status_code == 200

    quest = await club_reward_service.create_grant(db_session, club_id, "quest", "Задание", Bundle(coins=100))
    shop = await club_reward_service.create_grant(db_session, club_id, "shop", "Магазин", Bundle(coins=100))
    await db_session.commit()
    quest_id, shop_id = quest.id, shop.id

    told = (await db_session.execute(select(Notification.user_id).where(
        Notification.type == NotificationType.club_reward_available, Notification.related_object_id == quest_id,
    ))).scalars().all()
    assert told == [captain_id]

    newcomer = await db_session.get(User, newcomer_id)
    member = (await db_session.execute(select(ClubMember).where(ClubMember.user_id == newcomer_id))).scalar_one()
    assert await club_reward_service.unclaimed_count(db_session, member) == 1
    with pytest.raises(Exception, match="дольше 24 ч"):
        await club_reward_service.claim(db_session, newcomer, quest_id)
    await club_reward_service.claim(db_session, newcomer, shop_id)

    captain = await db_session.get(User, captain_id)
    await club_reward_service.claim(db_session, captain, quest_id)


async def test_war_reward_needs_the_minimum_points(client, db_session, bot_token):
    config = await get_config(db_session)
    config.club_war_start_weekday = (local_today() - week_start_for()).days
    config.club_war_start_hour = 0
    config.club_war_duration_hours = 48
    config.club_war_min_members = 1
    config.club_war_min_points = 4
    await db_session.commit()

    club_a, worker_id, _ = await _club(client, db_session, bot_token, 943001, "Вклад А")
    _club_b, _cap_b, _ = await _club(client, db_session, bot_token, 943002, "Вклад Б")
    passenger_id, headers_p = await _user(client, db_session, bot_token, 943003)
    assert (await client.post(f"/api/v1/clubs/{club_a}/join", headers=headers_p)).status_code == 200
    await client.post("/api/v1/internal/clubs/wars/sweep", headers=INTERNAL)

    for _ in range(3):
        db_session.add(GameSession(user_id=worker_id, game_type="memory_sequence", status=GameSessionStatus.won, created_at=NOW() - timedelta(minutes=2)))
    await db_session.commit()
    await _age_membership(db_session, worker_id, 72)
    await _age_membership(db_session, passenger_id, 72)

    war = (await db_session.execute(select(club_war_service.ClubWar))).scalar_one()
    war.ends_at = NOW() - timedelta(minutes=1)
    await db_session.commit()
    assert await club_war_service.settle_due(db_session) == 1

    grant = (await db_session.execute(select(ClubRewardGrant).where(ClubRewardGrant.source == "war"))).scalar_one()
    assert grant.eligible_user_ids == [worker_id]
    grant_id = grant.id
    passenger = await db_session.get(User, passenger_id)
    with pytest.raises(Exception, match="достаточно очков"):
        await club_reward_service.claim(db_session, passenger, grant_id)
    worker = await db_session.get(User, worker_id)
    await club_reward_service.claim(db_session, worker, grant_id)


async def test_lost_games_are_worth_less_and_quick_losses_nothing(client, db_session, bot_token):
    club_id, user_id, _ = await _club(client, db_session, bot_token, 944001, "Качество")
    rival_id, _ = await _user(client, db_session, bot_token, 944002)
    assert (await client.post(f"/api/v1/clubs/{club_id}/join", headers=_)).status_code == 200
    await _age_membership(db_session, user_id, 1)
    await _age_membership(db_session, rival_id, 1)
    now = NOW()
    session = lambda status, seconds: GameSession(  # noqa: E731
        user_id=user_id, game_type="memory_sequence", status=status,
        created_at=now - timedelta(minutes=10), finished_at=now - timedelta(minutes=10) + timedelta(seconds=seconds),
    )
    db_session.add_all([
        session(GameSessionStatus.won, 5),  # a quick win is still a win
        session(GameSessionStatus.lost, 60),
        session(GameSessionStatus.lost, 3),  # thrown away: not counted
        GameSession(user_id=user_id, game_type="memory_sequence", status=GameSessionStatus.lost, created_at=now - timedelta(minutes=9)),
    ])
    # The penalty result is the challenger's: the opponent is the one who lost.
    db_session.add(PenaltyMatch(
        user_id=rival_id, opponent_user_id=user_id, opponent_name="Соперник", status=PenaltyMatchStatus.finished, result=MatchResult.win,
        resolved_at=now - timedelta(minutes=5),
    ))
    await db_session.commit()

    tallies = await _activity(db_session, now - timedelta(hours=1), now + timedelta(hours=1), club_id=club_id)
    tally = tallies[(club_id, user_id)]
    assert (tally.games, tally.lost) == (4, 3)
    assert tallies[(club_id, rival_id)].lost == 0

    config = await get_config(db_session)
    config.club_league_points_game, config.club_league_lost_game_pct = 2, 50
    assert game_points(tally, config) == 2 + 3
    assert game_points(_Tally(games=1), config) == 2


async def test_absent_captain_hands_over_to_the_first_active_member(client, db_session, bot_token):
    club_id, captain_id, _ = await _club(client, db_session, bot_token, 945001, "Капитан")
    member_id, headers_m = await _user(client, db_session, bot_token, 945002)
    away_vice_id, headers_v = await _user(client, db_session, bot_token, 945003)
    vice_id, headers_a = await _user(client, db_session, bot_token, 945004)
    for headers in (headers_m, headers_v, headers_a):
        assert (await client.post(f"/api/v1/clubs/{club_id}/join", headers=headers)).status_code == 200

    # Not absent yet: nothing happens.
    assert await club_service.replace_absent_captains(db_session) == 0

    members = {m.user_id: m for m in (await db_session.execute(select(ClubMember).where(ClubMember.club_id == club_id))).scalars()}
    members[away_vice_id].role = ClubRole.vice_captain
    members[vice_id].role = ClubRole.assistant
    for uid, days in ((captain_id, 20), (away_vice_id, 30), (member_id, 1), (vice_id, 1)):
        (await db_session.get(User, uid)).last_seen_at = NOW() - timedelta(days=days)
    await db_session.commit()

    resp = await client.post("/api/v1/internal/clubs/captains/sweep", headers=INTERNAL)
    assert resp.status_code == 200 and resp.json() == {"transferred": 1}

    db_session.expire_all()
    club = await db_session.get(Club, club_id)
    assert club.captain_id == vice_id  # the absent vice is skipped
    members = {m.user_id: m.role for m in (await db_session.execute(select(ClubMember).where(ClubMember.club_id == club_id))).scalars()}
    assert members[vice_id] == ClubRole.captain and members[captain_id] == ClubRole.member
    told = (await db_session.execute(select(Notification.user_id).where(
        Notification.type == NotificationType.club_captain_transferred,
    ))).scalars().all()
    assert set(told) == {vice_id, captain_id}
    assert (await client.post("/api/v1/internal/clubs/captains/sweep", headers=INTERNAL)).json() == {"transferred": 0}


async def test_a_club_with_nobody_active_keeps_its_captain(client, db_session, bot_token):
    club_id, captain_id, _ = await _club(client, db_session, bot_token, 946001, "Спящий")
    member_id, headers = await _user(client, db_session, bot_token, 946002)
    assert (await client.post(f"/api/v1/clubs/{club_id}/join", headers=headers)).status_code == 200
    for uid in (captain_id, member_id):
        (await db_session.get(User, uid)).last_seen_at = NOW() - timedelta(days=40)
    await db_session.commit()
    assert await club_service.replace_absent_captains(db_session) == 0
    db_session.expire_all()
    assert (await db_session.get(Club, club_id)).captain_id == captain_id

    config = await get_config(db_session)
    config.club_captain_absent_days = 0
    await db_session.commit()
    assert await club_service.replace_absent_captains(db_session) == 0

