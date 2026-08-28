import pytest_asyncio

from app.models.club import Club
from app.models.enums import Position
from app.schemas.club_ranking import ClubRankingMetric
from app.services.club_ranking_service import get_club_ranking
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """create_club seeds a starting squad on every creation — same seeding every other club test
    file needs (see test_clubs.py's identical fixture)."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _make_club(client, db_session, bot_token, telegram_id, name, cups=0, stars=0):
    await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    user = await get_user_by_telegram_id(db_session, telegram_id)
    resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(telegram_id, bot_token),
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    club = await db_session.get(Club, resp.json()["id"])
    club.cups_count = cups
    club.stars_count = stars
    db_session.add(club)
    await db_session.commit()
    return club, user


async def test_get_club_ranking_orders_by_metric_and_finds_me(client, db_session, bot_token):
    club_a, user_a = await _make_club(client, db_session, bot_token, 860001, "Клуб А", cups=5)
    club_b, _ = await _make_club(client, db_session, bot_token, 860002, "Клуб Б", cups=2)
    club_c, _ = await _make_club(client, db_session, bot_token, 860003, "Клуб В", cups=9)

    result = await get_club_ranking(db_session, ClubRankingMetric.cups, current_user_id=user_a.id)

    assert [e.club_id for e in result.top] == [club_c.id, club_a.id, club_b.id]
    assert [e.value for e in result.top] == [9, 5, 2]
    assert result.me is not None
    assert result.me.club_id == club_a.id
    assert result.me.rank == 2


async def test_get_club_ranking_me_is_none_when_not_in_a_club(client, db_session, bot_token):
    await _make_club(client, db_session, bot_token, 860004, "Клуб Г", stars=1)
    await client.post("/api/v1/auth/session", headers=telegram_headers(860005, bot_token))
    outsider = await get_user_by_telegram_id(db_session, 860005)

    result = await get_club_ranking(db_session, ClubRankingMetric.stars, current_user_id=outsider.id)
    assert result.me is None


async def test_leaderboard_endpoint_returns_ranked_clubs(client, db_session, bot_token):
    await _make_club(client, db_session, bot_token, 860006, "Клуб Д", stars=4)
    resp = await client.get(
        "/api/v1/clubs/leaderboard", params={"metric": "stars"}, headers=telegram_headers(860006, bot_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["metric"] == "stars"
    assert body["top"][0]["value"] == 4
    assert body["top"][0]["name"] == "Клуб Д"
