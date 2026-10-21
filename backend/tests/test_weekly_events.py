"""«Неделя мини-игры» (leaderboard of the best N games, settled once, prizes
claimed once), «Матч дня» (guess before kickoff, reward tiers, claim once,
result locked after claims) and «Клубный рейд» (daily attack limit across
clubs, the boss is defeated once and pays the club)."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.club import Club
from app.models.club_reward import ClubRewardGrant
from app.models.enums import GameSessionStatus, GameType, NotificationType, Position
from app.models.game import GameSession
from app.models.notification import Notification
from app.models.user import User
from app.models.weekly_event import ClubRaid, MatchDayFixture, WeeklyCupResult, WeeklyCupWeek
from app.services import club_raid_service, weekly_cup_service
from app.services.club_league_service import week_bounds, week_start_for
from app.services.game_config_service import get_config
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1"


@pytest.fixture(autouse=True)
async def _seed(db_session):
    rate_limit_module._hits.clear()
    for position in (Position.GK, Position.CB, Position.CB, Position.LB, Position.RB, Position.CM, Position.CM,
                     Position.CAM, Position.LW, Position.RW, Position.ST, Position.ST):
        await create_player(db_session, position=position)
    await db_session.commit()


async def _register(client, db_session, telegram_id, bot_token):
    headers = telegram_headers(telegram_id, bot_token)
    assert (await client.post(f"{API}/auth/session", headers=headers)).status_code == 200
    return headers, await get_user_by_telegram_id(db_session, telegram_id)


def _session(db_session, user_id, game_type, at, score=0, reward=0, state=None):
    db_session.add(GameSession(user_id=user_id, game_type=game_type, status=GameSessionStatus.won, score=score,
                               reward_coins=reward, server_state=state, created_at=at, finished_at=at))


# --- «Неделя мини-игры» -------------------------------------------------------------------------

async def test_weekly_cup_counts_best_games_and_pays_once(client, db_session, bot_token):
    a_h, a = await _register(client, db_session, 920001, bot_token)
    b_h, b = await _register(client, db_session, 920002, bot_token)
    config = await get_config(db_session)
    config.weekly_cup_games = ["free_kick"]
    config.weekly_cup_best_of = 2
    config.weekly_cup_prizes = [700, 300]
    now = datetime.now(timezone.utc)
    for coins in (50, 40, 10):  # best two: 90
        _session(db_session, a.id, GameType.free_kick, now, reward=coins)
    _session(db_session, b.id, GameType.free_kick, now, reward=80)
    _session(db_session, b.id, GameType.memory_sequence, now, score=500)  # another game doesn't count
    await db_session.commit()

    view = (await client.get(f"{API}/weekly-cup", headers=b_h)).json()
    assert view["game"] == "free_kick" and view["participants"] == 2
    assert [(r["name"] is not None, r["points"], r["games"]) for r in view["top"]] == [(True, 90, 2), (True, 80, 1)]
    assert view["me"] == {"place": 2, "points": 80, "games": 1}

    # The week ends: the next read settles it once.
    last = week_start_for()
    row = await db_session.get(WeeklyCupWeek, last)
    row.week_start = last - timedelta(days=7)
    for s in (await db_session.execute(select(GameSession))).scalars():
        s.finished_at = s.finished_at - timedelta(days=7)
    await db_session.commit()
    view = (await client.get(f"{API}/weekly-cup", headers=a_h)).json()
    assert view["last_week"]["place"] == 1 and view["last_week"]["prize"] == 700 and view["unclaimed_coins"] == 700
    assert view["participants"] == 0
    assert await weekly_cup_service.settle(db_session, last - timedelta(days=7)) is False
    assert len((await db_session.execute(select(WeeklyCupResult))).scalars().all()) == 2
    notes = (await db_session.execute(select(Notification).where(Notification.type == NotificationType.weekly_cup_result))).scalars().all()
    assert {n.user_id for n in notes} == {a.id, b.id}

    balance = (await db_session.get(User, a.id)).balance
    claimed = await client.post(f"{API}/weekly-cup/claim", headers=a_h)
    assert claimed.status_code == 200 and claimed.json()["coins"] == 700
    assert claimed.json()["new_balance"] == balance + 700
    assert (await client.post(f"{API}/weekly-cup/claim", headers=a_h)).status_code == 409


async def test_weekly_cup_penalty_points_and_blocked_players(client, db_session, bot_token):
    a_h, a = await _register(client, db_session, 920011, bot_token)
    _b_h, b = await _register(client, db_session, 920012, bot_token)
    config = await get_config(db_session)
    config.weekly_cup_games = ["penalty"]
    now = datetime.now(timezone.utc)
    _session(db_session, a.id, GameType.penalty, now, state={"player_score": 4, "bot_score": 2})  # 40 + 30
    _session(db_session, a.id, GameType.penalty, now, state={"player_score": 2, "bot_score": 3})  # 20
    _session(db_session, b.id, GameType.penalty, now, state={"player_score": 5, "bot_score": 0})
    (await db_session.get(User, b.id)).game_rewards_blocked = True
    await db_session.commit()
    view = (await client.get(f"{API}/weekly-cup", headers=a_h)).json()
    assert [r["points"] for r in view["top"]] == [90] and view["top"][0]["is_me"]


# --- «Матч дня» ---------------------------------------------------------------------------------

async def test_match_day_predict_until_kickoff_and_claim_tiers(client, db_session, bot_token):
    a_h, a = await _register(client, db_session, 920021, bot_token)
    b_h, _b = await _register(client, db_session, 920022, bot_token)
    c_h, _c = await _register(client, db_session, 920023, bot_token)
    token = (await client.post(f"{API}/auth/session", headers=telegram_headers(999000001, bot_token))).json()["admin_token"]
    (await get_config(db_session)).match_day_enabled = True  # off by default
    await db_session.commit()
    admin_h = {"Authorization": f"Bearer {token}"}
    kickoff = datetime.now(timezone.utc) + timedelta(hours=3)
    created = await client.post(f"{API}/admin/match-day", headers=admin_h,
                                json={"home": "Спартак", "away": "ЦСКА", "league": "РПЛ", "kickoff_at": kickoff.isoformat()})
    assert created.status_code == 200, created.text
    view = (await client.get(f"{API}/match-day", headers=a_h)).json()
    fid = view["current"]["id"]
    assert view["current"]["open"] and view["current"]["prediction"] is None

    for headers, (h, aw) in ((a_h, (2, 1)), (b_h, (3, 2)), (c_h, (0, 0))):
        resp = await client.put(f"{API}/match-day/{fid}/prediction", headers=headers, json={"home": h, "away": aw})
        assert resp.status_code == 200, resp.text
    again = (await client.put(f"{API}/match-day/{fid}/prediction", headers=a_h, json={"home": 2, "away": 0})).json()
    assert again["current"]["prediction"] == {"home": 2, "away": 0}
    assert again["current"]["split"] == {"home": 2, "draw": 1, "away": 0, "total": 3}
    assert (await client.post(f"{API}/match-day/{fid}/claim", headers=a_h)).status_code == 409  # no result yet

    fixture = await db_session.get(MatchDayFixture, fid)
    fixture.kickoff_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()
    assert (await client.put(f"{API}/match-day/{fid}/prediction", headers=a_h, json={"home": 1, "away": 0})).status_code == 409

    assert (await client.patch(f"{API}/admin/match-day/{fid}", headers=admin_h, json={"home_score": 3, "away_score": 1})).status_code == 200
    config = await get_config(db_session)
    a_claim = (await client.post(f"{API}/match-day/{fid}/claim", headers=a_h)).json()  # 2:0 → same difference
    b_claim = (await client.post(f"{API}/match-day/{fid}/claim", headers=b_h)).json()  # 3:2 → outcome
    c_claim = (await client.post(f"{API}/match-day/{fid}/claim", headers=c_h)).json()  # 0:0 → miss
    assert (a_claim["coins"], b_claim["coins"], c_claim["coins"]) == (config.match_day_diff_coins, config.match_day_outcome_coins, 0)
    assert (await client.post(f"{API}/match-day/{fid}/claim", headers=a_h)).status_code == 409
    # Somebody claimed: the result is locked.
    assert (await client.patch(f"{API}/admin/match-day/{fid}", headers=admin_h, json={"home_score": 2, "away_score": 1})).status_code == 409
    recent = (await client.get(f"{API}/match-day", headers=a_h)).json()["recent"][0]
    assert recent["claimed"] and recent["reward_kind"] == "diff" and recent["home_score"] == 3


# --- «Клубный рейд» -----------------------------------------------------------------------------

async def _club(client, headers, name):
    resp = await client.post(f"{API}/clubs", headers=headers, json={
        "name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#00FF00",
    })
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def test_raid_daily_limit_and_boss_defeated_once(client, db_session, bot_token):
    cap_h, _cap = await _register(client, db_session, 920031, bot_token)
    club_id = await _club(client, cap_h, "Рейдеры")
    config = await get_config(db_session)
    config.club_raid_attacks_per_day = 2
    config.club_raid_hp_per_member = 1000  # 3 members minimum → 3000 HP: two attacks (≤ 699 each) never finish it
    config.club_raid_reward_budget = 500
    await db_session.commit()

    view = (await client.get(f"{API}/clubs/me/raid", headers=cap_h)).json()
    assert view["hp"] == 3000 and view["damage"] == 0 and view["attacks_left"] == 2 and not view["defeated"]
    budget = (await db_session.get(Club, club_id)).budget

    first = await client.post(f"{API}/clubs/me/raid/attack", headers=cap_h)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["last"]["damage"] >= view["strength"] and body["attacks_left"] == 1
    assert len(body["last"]["shots"]) == config.club_raid_shots
    second = (await client.post(f"{API}/clubs/me/raid/attack", headers=cap_h)).json()
    # Strength alone (50+) twice plus any goals: the boss of 300 HP may or may not fall — force it.
    raid = (await db_session.execute(select(ClubRaid).where(ClubRaid.club_id == club_id))).scalar_one()
    assert raid.damage == body["last"]["damage"] + second["last"]["damage"]
    assert (await client.post(f"{API}/clubs/me/raid/attack", headers=cap_h)).status_code == 409  # daily limit

    if raid.defeated_at is None:
        raid.hp = raid.damage + 1
        await db_session.commit()
        member_h, _m = await _register(client, db_session, 920032, bot_token)
        await client.post(f"{API}/clubs/{club_id}/join", headers=member_h)
        finishing = (await client.post(f"{API}/clubs/me/raid/attack", headers=member_h)).json()
        assert finishing["last"]["defeated_now"] and finishing["defeated"]
        assert (await client.post(f"{API}/clubs/me/raid/attack", headers=member_h)).status_code == 409  # already beaten
    await db_session.refresh(raid)
    assert raid.defeated_at is not None
    await db_session.refresh(await db_session.get(Club, club_id))
    assert (await db_session.get(Club, club_id)).budget == budget + 500
    grants = (await db_session.execute(select(ClubRewardGrant).where(ClubRewardGrant.source == "raid"))).scalars().all()
    assert len(grants) == 1


async def test_raid_limit_counts_across_clubs(client, db_session, bot_token):
    a_h, _a = await _register(client, db_session, 920041, bot_token)
    b_h, _b = await _register(client, db_session, 920042, bot_token)
    club_a = await _club(client, a_h, "Клуб А")
    await _club(client, b_h, "Клуб Б")
    config = await get_config(db_session)
    config.club_raid_attacks_per_day = 1
    await db_session.commit()
    hopper_h, _h = await _register(client, db_session, 920043, bot_token)
    await client.post(f"{API}/clubs/{club_a}/join", headers=hopper_h)
    assert (await client.post(f"{API}/clubs/me/raid/attack", headers=hopper_h)).status_code == 200
    await client.post(f"{API}/clubs/me/leave", headers=hopper_h)
    view = (await client.get(f"{API}/clubs/me/raid", headers=hopper_h))
    assert view.status_code == 404  # not in a club now


def test_goal_chance_grows_with_strength():
    assert club_raid_service.goal_chance(50) < club_raid_service.goal_chance(70) < club_raid_service.goal_chance(90)
    assert 0.15 <= club_raid_service.goal_chance(10) and club_raid_service.goal_chance(99) <= 0.8


def test_week_rotation_is_stable():
    config = type("C", (), {"weekly_cup_games": ["penalty", "memory"]})()
    week = week_start_for()
    assert weekly_cup_service.game_of_week(week, config) == weekly_cup_service.game_of_week(week, config)
    assert {weekly_cup_service.game_of_week(week + timedelta(days=7 * i), config) for i in range(2)} == {"penalty", "memory"}
    assert week_bounds(date(2026, 10, 19))[1] - week_bounds(date(2026, 10, 19))[0] == timedelta(days=7)
