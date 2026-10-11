"""«Карьера игрока»: clubs built from cards, contract rules, a full season
with personal stats, rewards, reputation, awards and transfer offers."""
from datetime import datetime, timedelta, timezone

import pytest

import app.core.rate_limit as rate_limit_module
from app.models.enums import Position
from app.models.my_player import MyPlayer
from app.models.player_career import PlayerCareerSeason
from app.models.trophy import TrophyDefinition
from app.models.user import User
from app.services import my_player_service, player_career_service
from app.services.game_config_service import get_config
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1"
LOOK = {"skin": 1, "hair": 1, "hair_color": 1, "beard": 0, "eye_color": 0, "kit": 0, "kit_pattern": 0}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _club(db_session, name: str, rating: int, n: int = 6):
    positions = [Position.GK, Position.CB, Position.CB, Position.CM, Position.ST, Position.LW, Position.RB][:n]
    for pos in positions:
        player = await create_player(db_session, rating=rating, position=pos)
        player.club = name
    await db_session.commit()


async def _player(client, db_session, bot_token, tg_id):
    headers = telegram_headers(tg_id, bot_token)
    await client.post(f"{API}/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, tg_id)
    resp = await client.post(f"{API}/my-player", headers=headers,
                             json={"name": "Карьерист", "number": 9, "position": "ST", "appearance": LOOK})
    assert resp.status_code == 200, resp.text
    return user.id, headers


async def test_clubs_from_cards_and_contract_rules(client, db_session, bot_token):
    await _club(db_session, "Барселона", 86)
    await _club(db_session, "Мини", 70, n=3)  # too few cards → not a club
    user_id, headers = await _player(client, db_session, bot_token, 880001)

    view = (await client.get(f"{API}/player-career", headers=headers)).json()
    clubs = {c["name"]: c for c in view["clubs"]}
    assert "Мини" not in clubs
    barca = clubs["Барселона"]
    assert barca["real_cards"] == 6 and barca["locked_reason"] and not barca["is_demo"]
    assert clubs["Юность"]["is_demo"] and clubs["Юность"]["locked_reason"] is None
    # Academy fills the XI: 6 real cards + 5 academy players.
    catalog = await player_career_service.club_catalog(db_session, await get_config(db_session))
    squad = next(c for c in catalog if c["name"] == "Барселона")["squad"]
    assert len(squad) == 11 and sum(1 for p in squad if p["academy"]) == 5

    assert (await client.post(f"{API}/player-career/contract", headers=headers, json={"club_key": barca["key"]})).status_code == 409
    assert (await client.post(f"{API}/player-career/seasons", headers=headers)).status_code == 409  # no club yet
    resp = await client.post(f"{API}/player-career/contract", headers=headers, json={"club_key": clubs["Юность"]["key"]})
    assert resp.status_code == 200 and resp.json()["club"]["name"] == "Юность"


async def test_full_season_stats_rewards_awards_and_offers(client, db_session, bot_token):
    await _club(db_session, "Барселона", 86)
    db_session.add_all([
        TrophyDefinition(code="player_career_champion", name="Чемпион лиги", is_active=True),
        TrophyDefinition(code="player_career_top_scorer", name="Лучший бомбардир", is_active=True),
        TrophyDefinition(code="player_career_mvp", name="Игрок сезона", is_active=True),
    ])
    await db_session.commit()
    user_id, headers = await _player(client, db_session, bot_token, 880002)
    clubs = {c["name"]: c for c in (await client.get(f"{API}/player-career", headers=headers)).json()["clubs"]}
    await client.post(f"{API}/player-career/contract", headers=headers, json={"club_key": clubs["Юность"]["key"]})

    resp = await client.post(f"{API}/player-career/seasons", headers=headers)
    assert resp.status_code == 200, resp.text
    season = resp.json()["season"]
    assert season["status"] == "active" and len(season["teams"]) == 8 and season["teams"][0]["is_mine"]
    assert len(season["rounds"]) == 14
    assert (await client.post(f"{API}/player-career/seasons", headers=headers)).status_code == 409
    other = clubs["Заря"]["key"]
    assert (await client.post(f"{API}/player-career/contract", headers=headers, json={"club_key": other})).status_code == 409

    # Make the player a star before the season ends so a big club opens up.
    mp = (await db_session.get(MyPlayer, (await my_player_service.get_my_player(db_session, user_id)).id))
    mp.attributes = {"atk": 99, "def": 80}
    mp.reputation = 500
    await db_session.commit()
    balance_before = (await db_session.get(User, user_id)).balance

    later = datetime.now(timezone.utc) + timedelta(days=8)
    assert await player_career_service.resolve_due(db_session, season["id"], now=later) == 14
    assert await player_career_service.resolve_due(db_session, season["id"], now=later) == 0

    db_session.expire_all()
    row = await db_session.get(PlayerCareerSeason, season["id"])
    assert row.status == "finished" and row.final_place is not None and row.coins_earned > 0
    assert (await db_session.get(User, user_id)).balance == balance_before + row.coins_earned
    my_rounds = list(row.state["my_rounds"].values())
    assert len(my_rounds) == 14 and all(r["played"] and 4.0 <= r["rating"] <= 10.0 for r in my_rounds)
    # Personal goals never exceed the team's goals.
    assert all(r["goals"] <= r["own"] for r in my_rounds)
    mp = await my_player_service.get_my_player(db_session, user_id)
    assert mp.career_stats["seasons"] == 1 and mp.career_stats["matches"] == 14
    assert mp.career_stats["goals"] == sum(r["goals"] for r in my_rounds)
    assert any(o["name"] == "Барселона" for o in row.state["offers"])
    if row.final_place == 1:
        assert "Чемпион лиги" in row.state["awards"]

    # Between seasons the offered club can be signed.
    view = (await client.get(f"{API}/player-career", headers=headers)).json()
    assert view["season"]["status"] == "finished" and view["can_change_club"]
    barca = next(o for o in view["season"]["offers"] if o["name"] == "Барселона")
    resp = await client.post(f"{API}/player-career/contract", headers=headers, json={"club_key": barca["key"]})
    assert resp.status_code == 200 and resp.json()["club"]["name"] == "Барселона"


async def test_view_without_player(client, db_session, bot_token):
    headers = telegram_headers(880003, bot_token)
    await client.post(f"{API}/auth/session", headers=headers)
    view = (await client.get(f"{API}/player-career", headers=headers)).json()
    assert view["has_player"] is False and view["clubs"] == []
