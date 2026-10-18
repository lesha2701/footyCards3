"""«Лига клубов» divisions: per-division weekly tables and prizes, season
promotion/relegation, and the trophy room."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.club import Club
from app.models.club_league import ClubLeagueResult, ClubLeagueWeek, ClubSeasonResult
from app.models.enums import GameSessionStatus, NotificationType, Position
from app.models.game import GameSession
from app.models.notification import Notification
from app.services import club_league_service
from app.services.game_config_service import get_config
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
async def _seed(db_session):
    rate_limit_module._hits.clear()
    for position in (Position.GK, Position.GK, Position.LB, Position.LB, Position.CB, Position.CB, Position.RB,
                     Position.RB, Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM, Position.LW,
                     Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _club(client, db_session, bot_token, telegram_id, name, division=0):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    club_id = (await client.post("/api/v1/clubs", headers=headers, json={
        "name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000",
    })).json()["id"]
    club = await db_session.get(Club, club_id)
    club.league_division = division
    await db_session.commit()
    return club_id, await get_user_by_telegram_id(db_session, telegram_id), headers


def _games(db_session, user_id, count):
    for _ in range(count):
        db_session.add(GameSession(user_id=user_id, game_type="memory_sequence", status=GameSessionStatus.won,
                                   created_at=datetime.now(timezone.utc)))


async def test_season_end_promotes_relegates_and_pays_by_division(client, db_session, bot_token):
    a, cap_a, headers_a = await _club(client, db_session, bot_token, 920001, "Бронза А")
    b, cap_b, _ = await _club(client, db_session, bot_token, 920002, "Бронза Б")
    c, cap_c, _ = await _club(client, db_session, bot_token, 920003, "Серебро В", division=1)
    d, cap_d, headers_d = await _club(client, db_session, bot_token, 920004, "Серебро Г", division=1)
    _games(db_session, cap_a.id, 5)
    _games(db_session, cap_b.id, 2)
    _games(db_session, cap_d.id, 3)
    config = await get_config(db_session)
    config.club_league_rewards = [1000, 500]
    config.club_league_division_reward_pct = [100, 150, 200]
    config.club_league_season_weeks = 1  # every week ends a season
    config.club_league_promote_count = 1
    config.club_league_relegate_count = 1
    this_week = club_league_service.week_start_for()
    db_session.add(ClubLeagueWeek(week_start=this_week - timedelta(days=7), is_bootstrap=True))
    await db_session.commit()

    # Live: each division has its own table.
    body = (await client.get("/api/v1/clubs/league", headers=headers_d)).json()
    assert body["division"] == 1 and body["division_reward_pct"] == 150
    assert [r["club_id"] for r in body["table"]] == [d]
    assert body["table"][0]["reward"] == 1500
    assert [(r["club_id"], r["zone"]) for r in body["season"]["standings"]] == [(d, "up"), (c, "down")]

    budgets = {cid: (await db_session.get(Club, cid)).budget for cid in (a, b, c, d)}
    ids = {"a": cap_a.id, "c": cap_c.id, "d": cap_d.id}
    next_week = datetime.now(timezone.utc) + timedelta(days=7)
    await club_league_service.settle_due(db_session, now=next_week)

    db_session.expire_all()
    clubs = {cid: await db_session.get(Club, cid) for cid in (a, b, c, d)}
    assert clubs[a].budget == budgets[a] + 1000
    assert clubs[b].budget == budgets[b] + 500
    assert clubs[d].budget == budgets[d] + 1500
    assert clubs[c].budget == budgets[c]
    assert {cid: clubs[cid].league_division for cid in clubs} == {a: 1, b: 0, c: 0, d: 2}

    results = (await db_session.execute(select(ClubLeagueResult))).scalars().all()
    assert {(r.club_id, r.division, r.rank) for r in results} == {(a, 0, 1), (b, 0, 2), (d, 1, 1)}
    seasons = {s.club_id: s for s in (await db_session.execute(select(ClubSeasonResult))).scalars()}
    assert {cid: (s.division, s.rank, s.moved) for cid, s in seasons.items()} == {
        a: (0, 1, 1), b: (0, 2, 0), d: (1, 1, 1), c: (1, 2, -1),
    }
    promoted = (await db_session.execute(select(Notification.user_id).where(
        Notification.type == NotificationType.club_league_promoted,
    ))).scalars().all()
    relegated = (await db_session.execute(select(Notification.user_id).where(
        Notification.type == NotificationType.club_league_relegated,
    ))).scalars().all()
    assert set(promoted) == {ids["a"], ids["d"]} and set(relegated) == {ids["c"]}

    trophies = (await client.get(f"/api/v1/clubs/{a}/trophies", headers=headers_d)).json()
    assert trophies["division"] == 1 and trophies["division_name"] == "Серебряная лига"
    assert trophies["league_gold"] == 1
    assert [(s["division"], s["rank"], s["moved"]) for s in trophies["seasons"]] == [(0, 1, 1)]
    assert (await client.get("/api/v1/clubs/999999/trophies", headers=headers_a)).status_code == 404


async def test_top_division_never_promotes_and_bottom_never_relegates(client, db_session, bot_token):
    g, cap_g, _ = await _club(client, db_session, bot_token, 920011, "Золото", division=2)
    z, _cap_z, _ = await _club(client, db_session, bot_token, 920012, "Бронза ноль")
    _games(db_session, cap_g.id, 4)
    config = await get_config(db_session)
    config.club_league_season_weeks = 1
    db_session.add(ClubLeagueWeek(week_start=club_league_service.week_start_for() - timedelta(days=7), is_bootstrap=True))
    await db_session.commit()
    await club_league_service.settle_due(db_session, now=datetime.now(timezone.utc) + timedelta(days=7))
    db_session.expire_all()
    assert (await db_session.get(Club, g)).league_division == 2
    assert (await db_session.get(Club, z)).league_division == 0
