"""«Карьера игрока»: the shared «Карьера тренера» club list (divisions =
leagues), rating + prestige gates, contracts and the transfer window with
haggling, a full season, the Champions League, the national team and the
«Золотой мяч»."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.career import CareerClub
from app.models.enums import Position, TransactionType
from app.models.my_player import MyPlayer
from app.models.player_career import PlayerCareerCup, PlayerCareerGoldenBall, PlayerCareerMonthStat, PlayerCareerSeason
from app.models.transaction import CoinTransaction
from app.models.trophy import TrophyDefinition, UserTrophy
from app.models.user import User
from app.services import my_player_service, player_career_clubs, player_career_cups, player_career_service
from app.services.game_config_service import get_config
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1"
LOOK = {"skin": 1, "hair": 1, "hair_color": 1, "beard": 0, "eye_color": 0, "kit": 0, "kit_pattern": 0}
TROPHIES = [
    ("player_career_champion", "Чемпион лиги"), ("player_career_top_scorer", "Лучший бомбардир"),
    ("player_career_mvp", "Игрок сезона"), ("player_career_cl_winner", "Победитель Лиги чемпионов"),
    ("player_career_national_winner", "Чемпион турнира сборных"), ("player_career_golden_ball", "Золотой мяч"),
]


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


class _Rng:
    """Deterministic stand-in for random.Random in haggling."""

    def __init__(self, value: float):
        self.value = value

    def random(self) -> float:
        return self.value


async def _barcelona(db_session, rating: int = 86, n: int = 6):
    positions = [Position.GK, Position.CB, Position.CB, Position.CM, Position.ST, Position.LW, Position.RB][:n]
    for pos in positions:
        player = await create_player(db_session, rating=rating, position=pos, country="Испания")
        player.club = "Барселона"
    db_session.add(CareerClub(name="Барселона", division=1, source="real", pool_club="Барселона"))
    db_session.add_all([TrophyDefinition(code=code, name=name, is_active=True) for code, name in TROPHIES])
    await db_session.commit()


async def _player(client, db_session, bot_token, tg_id, **extra):
    headers = telegram_headers(tg_id, bot_token)
    await client.post(f"{API}/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, tg_id)
    resp = await client.post(f"{API}/my-player", headers=headers,
                             json={"name": "Карьерист", "number": 9, "position": "ST", "appearance": LOOK, **extra})
    assert resp.status_code == 200, resp.text
    return user.id, headers


async def _view(client, headers):
    resp = await client.get(f"{API}/player-career", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _lowest_open(view):
    return min((c for c in view["clubs"] if not c["locked_reason"]), key=lambda c: (-c["level"], c["rating"]))


async def test_shared_club_list_rating_and_prestige_gates(client, db_session, bot_token):
    await _barcelona(db_session)
    user_id, headers = await _player(client, db_session, bot_token, 880001)

    view = await _view(client, headers)
    clubs = {c["name"]: c for c in view["clubs"]}
    barca = clubs["Барселона"]
    assert barca["level"] == 1 and barca["league"]["name"] == "Высшая лига" and barca["real_cards"] == 6
    assert barca["club_stars"] >= 4 and "рейтинг" in barca["locked_reason"]
    # Every division of «Карьера тренера» is there (filled automatically).
    assert {c["level"] for c in view["clubs"]} == {1, 2, 3, 4, 5}
    assert any(not c["locked_reason"] for c in view["clubs"] if c["level"] == 5)

    # A star with no prestige still can't sign for Barcelona.
    mp = await my_player_service.get_my_player(db_session, user_id)
    mp.attributes = {"atk": 99, "def": 90}
    await db_session.commit()
    barca = next(c for c in (await _view(client, headers))["clubs"] if c["name"] == "Барселона")
    config = await get_config(db_session)
    need = barca["reputation_needed"]
    assert need == config.player_career_star_prestige[barca["club_stars"] - 1] + config.player_career_level_prestige[0]
    assert barca["locked_reason"] == f"Нужен престиж {need}"
    mp.reputation = need
    await db_session.commit()
    barca = next(c for c in (await _view(client, headers))["clubs"] if c["name"] == "Барселона")
    assert barca["locked_reason"] is None
    # Salary grows with prestige.
    low_prestige = player_career_clubs.market_salary({"level": 1, "stars": barca["club_stars"]}, 0, config)
    assert barca["salary"] > low_prestige

    resp = await client.post(f"{API}/player-career/contract", headers=headers, json={"club_key": barca["key"]})
    assert resp.status_code == 200, resp.text
    contract = resp.json()["contract"]
    assert resp.json()["club"]["name"] == "Барселона"
    assert contract["seasons_left"] == config.player_career_contract_seasons and contract["salary"] == barca["salary"]
    # While the contract runs, clubs change only through offers.
    other = _lowest_open(resp.json())
    assert (await client.post(f"{API}/player-career/contract", headers=headers, json={"club_key": other["key"]})).status_code == 409


async def test_full_season_in_own_division_salary_and_contract(client, db_session, bot_token):
    user_id, headers = await _player(client, db_session, bot_token, 880002)
    view = await _view(client, headers)
    club = _lowest_open(view)
    signed = (await client.post(f"{API}/player-career/contract", headers=headers, json={"club_key": club["key"]})).json()
    salary = signed["contract"]["salary"]
    season = (await client.post(f"{API}/player-career/seasons", headers=headers)).json()["season"]
    assert season["league"]["level"] == club["level"]
    db_session.expire_all()
    row = await db_session.get(PlayerCareerSeason, season["id"])
    levels = {c["level"] for c in await player_career_clubs.club_catalog(db_session, await get_config(db_session))
              if c["key"] in {t.get("key") for t in row.state["teams"]}}
    assert levels == {club["level"]}

    later = datetime.now(timezone.utc) + timedelta(days=8)
    assert await player_career_service.resolve_due(db_session, season["id"], now=later) == 14
    db_session.expire_all()
    row = await db_session.get(PlayerCareerSeason, season["id"])
    assert row.status == "finished" and row.state["salary"] == salary
    mp = await db_session.get(MyPlayer, (await my_player_service.get_my_player(db_session, user_id)).id)
    assert mp.contract_seasons_left == (await get_config(db_session)).player_career_contract_seasons - 1
    month = await db_session.execute(select(PlayerCareerMonthStat).where(PlayerCareerMonthStat.user_id == user_id))
    played = sum(1 for v in row.state["my_rounds"].values() if v["played"])
    assert sum(m.matches for m in month.scalars().all()) == played
    view = await _view(client, headers)
    assert view["history"][0]["matches"] == played and not view["contract"]["expired"]
    # Contract still running: no renewal offer, the next season starts with the same club.
    assert not any(o["renewal"] for o in view["season"]["offers"])
    assert (await client.post(f"{API}/player-career/seasons", headers=headers)).status_code == 200


async def _finished_season_with_expired_contract(client, db_session, bot_token, tg_id):
    user_id, headers = await _player(client, db_session, bot_token, tg_id)
    club = _lowest_open(await _view(client, headers))
    await client.post(f"{API}/player-career/contract", headers=headers, json={"club_key": club["key"]})
    mp = await my_player_service.get_my_player(db_session, user_id)
    mp.contract_seasons_left = 1
    await db_session.commit()
    season = (await client.post(f"{API}/player-career/seasons", headers=headers)).json()["season"]
    await player_career_service.resolve_due(db_session, season["id"], now=datetime.now(timezone.utc) + timedelta(days=8))
    return user_id, headers, club


async def test_transfer_window_haggle_and_accept(client, db_session, bot_token):
    user_id, headers, club = await _finished_season_with_expired_contract(client, db_session, bot_token, 880003)
    view = await _view(client, headers)
    assert view["contract"]["expired"]
    assert (await client.post(f"{API}/player-career/seasons", headers=headers)).status_code == 409
    renewal = next(o for o in view["season"]["offers"] if o["renewal"])
    assert renewal["key"] == club["key"] and renewal["status"] == "open"

    user = await db_session.get(User, user_id)
    agreed = await player_career_service.counter_offer(db_session, user, renewal["key"], 20, rng=_Rng(0.0))
    offer = next(o for o in agreed["season"]["offers"] if o["key"] == renewal["key"])
    assert agreed["haggle"]["agreed"] and offer["counters"] == 1 and offer["last"] == "agreed"
    assert offer["salary"] == round(renewal["salary"] * 1.2 / 10) * 10

    balance = (await db_session.get(User, user_id)).balance
    resp = await client.post(f"{API}/player-career/offers/{renewal['key']}/accept", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["contract"]["salary"] == offer["salary"] and not body["contract"]["expired"]
    assert body["season"]["offers"][0]["status"] in ("accepted", "closed")
    db_session.expire_all()
    assert (await db_session.get(User, user_id)).balance == balance + offer["bonus"]
    assert (await client.post(f"{API}/player-career/offers/{renewal['key']}/accept", headers=headers)).status_code == 409


async def test_walked_away_means_lower_divisions_only(client, db_session, bot_token):
    await _barcelona(db_session)
    user_id, headers, club = await _finished_season_with_expired_contract(client, db_session, bot_token, 880004)
    user = await db_session.get(User, user_id)
    view = await _view(client, headers)
    for offer in view["season"]["offers"]:
        walked = await player_career_service.counter_offer(db_session, user, offer["key"], 30, rng=_Rng(0.99))
        assert not walked["haggle"]["agreed"]
    view = await _view(client, headers)
    assert all(o["status"] == "withdrawn" for o in view["season"]["offers"])
    config = await get_config(db_session)
    top = [c for c in view["clubs"] if c["level"] < config.player_career_free_agent_level]
    assert top and all(c["locked_reason"] for c in top)
    bad = next(c for c in view["clubs"] if c["name"] == "Барселона")
    assert (await client.post(f"{API}/player-career/contract", headers=headers, json={"club_key": bad["key"]})).status_code == 409
    low = next(c for c in view["clubs"] if not c["locked_reason"])
    assert low["level"] >= config.player_career_free_agent_level
    assert (await client.post(f"{API}/player-career/contract", headers=headers, json={"club_key": low["key"]})).status_code == 200


async def test_champions_league_knockout(client, db_session, bot_token):
    await _barcelona(db_session)
    user_id, headers = await _player(client, db_session, bot_token, 880005)
    await _view(client, headers)  # builds the club list
    config = await get_config(db_session)
    clubs = await player_career_clubs.club_catalog(db_session, config)
    mine = next(c for c in clubs if c["level"] == 1)
    cup = await player_career_cups.create_cl(db_session, user_id, 999, mine, config, datetime.now(timezone.utc))
    cup_id, teams = cup.id, cup.state["teams"]
    await db_session.commit()
    assert len(teams) == 8 and teams[0]["key"] == mine["key"]
    mp = await my_player_service.get_my_player(db_session, user_id)
    mp.club_key, mp.contract_seasons_left = mine["key"], 1
    await db_session.commit()
    assert (await client.post(f"{API}/player-career/seasons", headers=headers)).status_code == 409  # CL first

    played = await player_career_cups.resolve_cup(db_session, cup_id, now=datetime.now(timezone.utc) + timedelta(days=3))
    db_session.expire_all()
    cup = await db_session.get(PlayerCareerCup, cup_id)
    assert cup.status == "finished" and 1 <= played <= 3
    view = await _view(client, headers)
    shown = next(c for c in view["cups"] if c["kind"] == "cl")
    assert shown["title"] == "Лига чемпионов" and shown["rounds"][0]["label"] == "1/4 финала"
    if cup.state["won"]:
        trophies = (await client.get(f"{API}/my-player", headers=headers)).json()["trophies"]
        assert "Победитель Лиги чемпионов" in [t["name"] for t in trophies]
    assert (await client.post(f"{API}/player-career/seasons", headers=headers)).status_code == 200


async def test_national_team_call_up_once_per_window(client, db_session, bot_token):
    await _barcelona(db_session)
    user_id, headers = await _player(client, db_session, bot_token, 880006, country="Испания")
    view = await _view(client, headers)
    assert view["national"]["country"] == "Испания" and not view["national"]["called_up"]
    assert not view["cups"]
    mp = await my_player_service.get_my_player(db_session, user_id)
    mp.reputation = (await get_config(db_session)).player_career_national_prestige
    await db_session.commit()
    view = await _view(client, headers)
    assert view["national"]["called_up"]
    cup = next(c for c in view["cups"] if c["kind"] == "national")
    assert cup["my_team"] == "Испания" and len(cup["rounds"][0]["matches"]) == 4
    await _view(client, headers)
    count = (await db_session.execute(select(PlayerCareerCup).where(PlayerCareerCup.user_id == user_id))).scalars().all()
    assert len(count) == 1
    # Unknown country / changing it mid-tournament is refused.
    assert (await client.patch(f"{API}/my-player", headers=headers, json={"country": "Атлантида"})).status_code == 409
    assert (await client.patch(f"{API}/my-player", headers=headers, json={"country": "Бразилия"})).status_code == 409


async def test_golden_ball_awarded_once_for_last_month(client, db_session, bot_token):
    db_session.add_all([TrophyDefinition(code="player_career_golden_ball", name="Золотой мяч", is_active=True)])
    await db_session.commit()
    a_id, a_headers = await _player(client, db_session, bot_token, 880007)
    b_id, _ = await _player(client, db_session, bot_token, 880008)
    now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    db_session.add_all([
        PlayerCareerMonthStat(user_id=a_id, month="2026-10", matches=10, goals=9, assists=4, rating_sum=76.0),
        PlayerCareerMonthStat(user_id=b_id, month="2026-10", matches=10, goals=3, assists=1, rating_sum=68.0),
        PlayerCareerMonthStat(user_id=b_id, month="2026-09", matches=2, goals=9, assists=9, rating_sum=20.0),
    ])
    await db_session.commit()
    balance = (await db_session.get(User, a_id)).balance
    assert await player_career_cups.award_golden_ball(db_session, now) == a_id
    assert await player_career_cups.award_golden_ball(db_session, now) is None
    db_session.expire_all()
    config = await get_config(db_session)
    assert (await db_session.get(User, a_id)).balance == balance + config.player_career_golden_ball_coins
    row = await db_session.get(PlayerCareerGoldenBall, "2026-10")
    assert row.user_id == a_id and row.goals == 9
    trophies = (await db_session.execute(select(UserTrophy).where(UserTrophy.user_id == a_id))).scalars().all()
    assert len(trophies) == 1
    tx = (await db_session.execute(select(CoinTransaction).where(
        CoinTransaction.user_id == a_id, CoinTransaction.type == TransactionType.player_career_reward,
    ))).scalars().all()
    assert tx and "Золотой мяч" in tx[-1].description


async def test_view_without_player(client, db_session, bot_token):
    headers = telegram_headers(880009, bot_token)
    await client.post(f"{API}/auth/session", headers=headers)
    view = (await client.get(f"{API}/player-career", headers=headers)).json()
    assert view["has_player"] is False and view["clubs"] == []


async def test_club_gone_from_the_list_gives_a_free_pick(client, db_session, bot_token):
    user_id, headers = await _player(client, db_session, bot_token, 880010)
    mp = await my_player_service.get_my_player(db_session, user_id)
    mp.club_key, mp.contract_seasons_left = "demo:Юность", 1  # the old demo ladder
    await db_session.commit()
    view = await _view(client, headers)
    assert view["club"] is None and view["contract"] is None and view["can_change_club"]
    # Not a free agent: the higher divisions aren't locked for lack of a contract.
    assert not any("Без контракта" in (c["locked_reason"] or "") for c in view["clubs"])
    assert view["balance"] is not None


def test_every_line_can_win_the_golden_ball():
    """A typical month for each line lands close; a keeper's clean sheets count."""
    def row(line, goals, assists, clean, avg):
        return PlayerCareerMonthStat(
            user_id=1, month="2026-10", matches=14, goals=goals, assists=assists, clean_sheets=clean,
            rating_sum=avg * 14, line=line,
        )
    scores = {
        "FWD": player_career_cups.score_of(row("FWD", 8, 3, 0, 7.0)),
        "MID": player_career_cups.score_of(row("MID", 4, 4, 3, 6.9)),
        "DEF": player_career_cups.score_of(row("DEF", 1, 2, 4, 6.9)),
        "GK": player_career_cups.score_of(row("GK", 0, 0, 4, 6.8)),
    }
    assert max(scores.values()) - min(scores.values()) <= 6
    # The same month without clean sheets would leave a keeper far behind.
    assert player_career_cups.score_of(row("GK", 0, 0, 0, 6.8)) < scores["FWD"] - 20


def test_match_rating_rewards_clean_sheets_by_line():
    import random as _random

    gk = player_career_service._match_rating(0, 0, 1, 0, _random.Random(1), "GK")
    fwd = player_career_service._match_rating(0, 0, 1, 0, _random.Random(1), "FWD")
    assert round(gk - fwd, 1) == player_career_service.CLEAN_SHEET_BONUS["GK"]
    leaky = player_career_service._match_rating(0, 0, 1, 4, _random.Random(1), "GK")
    assert leaky < player_career_service._match_rating(0, 0, 1, 4, _random.Random(1), "FWD")
