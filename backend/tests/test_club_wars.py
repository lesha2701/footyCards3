"""«Клубные войны»: pairing by war rating, live score from members'
activity, idempotent start/settlement, prizes, Elo and the trophy room."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.config import get_settings
from app.core.timeutil import local_today
from app.models.club import Club
from app.models.club_reward import ClubRewardGrant
from app.models.club_war import ClubWar
from app.models.enums import GameSessionStatus, NotificationType, Position
from app.models.game import GameSession
from app.models.notification import Notification
from app.services import club_war_service
from app.services.club_league_service import week_start_for
from app.services.game_config_service import get_config
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

INTERNAL = {"X-Internal-Secret": get_settings().internal_api_secret}


@pytest.fixture(autouse=True)
async def _seed(db_session):
    rate_limit_module._hits.clear()
    for position in (Position.GK, Position.GK, Position.LB, Position.LB, Position.CB, Position.CB, Position.RB,
                     Position.RB, Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM, Position.LW,
                     Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)
    config = await get_config(db_session)
    # A window that is open right now: today 00:00 local, 48 h.
    config.club_war_start_weekday = (local_today() - week_start_for()).days
    config.club_war_start_hour = 0
    config.club_war_duration_hours = 48
    config.club_war_min_members = 1
    config.club_war_win_budget, config.club_war_draw_budget, config.club_war_loss_budget = 3000, 1500, 500
    config.club_war_win_member_coins = 200
    await db_session.commit()


async def _club(client, db_session, bot_token, telegram_id, name, rating):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    club_id = (await client.post("/api/v1/clubs", headers=headers, json={
        "name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000",
    })).json()["id"]
    club = await db_session.get(Club, club_id)
    club.war_rating = rating
    await db_session.commit()
    return club_id, (await get_user_by_telegram_id(db_session, telegram_id)).id, headers


def _games(db_session, user_id, count):
    for _ in range(count):
        db_session.add(GameSession(user_id=user_id, game_type="memory_sequence", status=GameSessionStatus.won,
                                   created_at=datetime.now(timezone.utc)))


async def test_war_pairs_scores_and_settles_once(client, db_session, bot_token):
    a, cap_a, headers_a = await _club(client, db_session, bot_token, 930001, "Война А", 1200)
    b, cap_b, headers_b = await _club(client, db_session, bot_token, 930002, "Война Б", 1150)
    c, _cap_c, _ = await _club(client, db_session, bot_token, 930003, "Война В", 1000)
    d, _cap_d, _ = await _club(client, db_session, bot_token, 930004, "Война Г", 900)
    e, _cap_e, headers_e = await _club(client, db_session, bot_token, 930005, "Без пары", 800)

    resp = await client.post("/api/v1/internal/clubs/wars/sweep", headers=INTERNAL)
    assert resp.status_code == 200 and resp.json() == {"started": 2, "settled": 0}
    assert (await client.post("/api/v1/internal/clubs/wars/sweep", headers=INTERNAL)).json() == {"started": 0, "settled": 0}
    wars = (await db_session.execute(select(ClubWar).order_by(ClubWar.id))).scalars().all()
    assert [(w.club_a_id, w.club_b_id) for w in wars] == [(a, b), (c, d)]
    started = (await db_session.execute(select(Notification.user_id).where(
        Notification.type == NotificationType.club_war_started,
    ))).scalars().all()
    assert cap_a in started and cap_b in started

    _games(db_session, cap_a, 5)
    _games(db_session, cap_b, 2)
    await db_session.commit()
    war = (await client.get("/api/v1/clubs/me/war", headers=headers_a)).json()
    assert war["state"] == "active" and war["opponent"]["club_id"] == b
    assert war["me"]["score"] == 10 and war["opponent"]["score"] == 4
    assert war["me"]["members"][0]["games"] == 5
    assert (await client.get("/api/v1/clubs/me/war", headers=headers_e)).json()["state"] == "none"

    budgets = {cid: (await db_session.get(Club, cid)).budget for cid in (a, b, c, d)}
    after = wars[0].ends_at.replace(tzinfo=timezone.utc) + timedelta(minutes=1)
    assert await club_war_service.settle_due(db_session, now=after) == 2
    assert await club_war_service.settle_due(db_session, now=after) == 0

    db_session.expire_all()
    clubs = {cid: await db_session.get(Club, cid) for cid in (a, b, c, d)}
    assert clubs[a].budget == budgets[a] + 3000
    assert clubs[b].budget == budgets[b] + 500
    assert clubs[c].budget == budgets[c] + 1500 and clubs[d].budget == budgets[d] + 1500
    assert clubs[a].war_rating > 1200 and clubs[b].war_rating < 1150
    assert clubs[c].war_rating < 1000 and clubs[d].war_rating > 900  # a draw against a weaker club costs rating
    settled = (await db_session.execute(select(ClubWar).order_by(ClubWar.id))).scalars().all()
    assert (settled[0].score_a, settled[0].score_b, settled[0].winner_club_id) == (10, 4, a)
    assert settled[1].winner_club_id is None

    grant = (await db_session.execute(select(ClubRewardGrant))).scalar_one()
    assert (grant.club_id, grant.source, grant.coins) == (a, "war", 200)
    finished = (await client.get("/api/v1/clubs/me/war", headers=headers_b)).json()
    assert finished["history"][0]["result"] == "loss" and finished["history"][0]["opponent_name"] == "Война А"

    trophies = (await client.get(f"/api/v1/clubs/{a}/trophies", headers=headers_a)).json()
    assert (trophies["wars_won"], trophies["wars_played"]) == (1, 1)


async def test_war_needs_min_members_and_can_be_switched_off(client, db_session, bot_token):
    await _club(client, db_session, bot_token, 930011, "Один", 1000)
    await _club(client, db_session, bot_token, 930012, "Два", 1000)
    config = await get_config(db_session)
    config.club_war_min_members = 2
    await db_session.commit()
    assert await club_war_service.start_due(db_session) == 0
    assert (await db_session.execute(select(ClubWar))).scalars().all() == []

    config = await get_config(db_session)
    config.club_war_enabled = False
    await db_session.commit()
    _, _, headers = await _club(client, db_session, bot_token, 930013, "Три", 1000)
    assert (await client.get("/api/v1/clubs/me/war", headers=headers)).json()["enabled"] is False
