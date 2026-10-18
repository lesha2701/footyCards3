"""«Карьера игрока» v3: key moments, role and the coach's trust, injuries,
story events, the friends' league with derbies, weekly rankings and tasks,
the daily chest, the Hall of Fame and the paid extras."""
import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.career import Friendship
from app.models.my_player import MyPlayer
from app.models.player_career import PlayerCareerClubRecord, PlayerCareerFriendLeague, PlayerCareerSeason
from app.models.trophy import TrophyDefinition, UserTrophy
from app.models.user import User
from app.services import (
    my_player_service,
    player_career_life as life,
    player_career_moments as moments,
    player_career_service,
)
from app.services.game_config_service import get_config
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1"
LOOK = {"skin": 1, "hair": 1, "hair_color": 1, "beard": 0, "eye_color": 0, "kit": 0, "kit_pattern": 0}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


class _Rng(random.Random):
    """random() always returns `value` — forces every roll one way."""

    def __init__(self, value: float):
        super().__init__(1)
        self.value = value

    def random(self) -> float:
        return self.value


async def _player(client, db_session, bot_token, tg_id, position="ST"):
    headers = telegram_headers(tg_id, bot_token)
    await client.post(f"{API}/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, tg_id)
    resp = await client.post(f"{API}/my-player", headers=headers,
                             json={"name": "Игрок " + "АБВГДЕЖЗИК"[tg_id % 10], "number": 9, "position": position, "appearance": LOOK})
    assert resp.status_code == 200, resp.text
    return user.id, headers


async def _signed(client, db_session, bot_token, tg_id, position="ST"):
    """A player at the weakest open club of the lowest division, trusted to start."""
    user_id, headers = await _player(client, db_session, bot_token, tg_id, position)
    view = (await client.get(f"{API}/player-career", headers=headers)).json()
    club = min((c for c in view["clubs"] if not c["locked_reason"]), key=lambda c: (-c["level"], c["rating"]))
    assert (await client.post(f"{API}/player-career/contract", headers=headers, json={"club_key": club["key"]})).status_code == 200
    mp = await my_player_service.get_my_player(db_session, user_id)
    mp.trust = 90
    mp.attributes = {"atk": 80, "def": 70}
    await db_session.commit()
    return user_id, headers, club


async def _first_round_pending(client, db_session, headers, user_id):
    season = (await client.post(f"{API}/player-career/seasons", headers=headers)).json()["season"]
    db_session.expire_all()
    row = await db_session.get(PlayerCareerSeason, season["id"])
    first = datetime.fromisoformat(row.state["schedule"][0])
    assert await player_career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=1)) == 1
    db_session.expire_all()
    return season["id"], await db_session.get(PlayerCareerSeason, season["id"])


async def test_key_moments_wait_for_decisions_then_finalize(client, db_session, bot_token):
    user_id, headers, _ = await _signed(client, db_session, bot_token, 891001)
    season_id, row = await _first_round_pending(client, db_session, headers, user_id)
    pending = row.state["pending"]
    config = await get_config(db_session)
    assert len(pending["moments"]) == config.player_career_moments
    assert all(m["kind"] == "attack" for m in pending["moments"])  # a forward attacks
    assert row.state["my_rounds"]["0"]["rating"] is None  # not final yet
    base_goals = row.state["my_rounds"]["0"]["goals"]
    base_own = row.state["my_rounds"]["0"]["own"]

    view = (await client.get(f"{API}/player-career", headers=headers)).json()
    shown = view["pending"]["moments"][0]
    assert {o["code"] for o in shown["options"]} == {"shot", "pass", "dribble"}
    assert all(o["chance_hit"] > o["chance"] for o in shown["options"])

    user = await db_session.get(User, user_id)
    after = await player_career_service.play_moment(db_session, user, 0, "shot", True, rng=_Rng(0.0))
    assert after["moment_result"]["success"] and after["pending"]["moments"][0]["status"] == "done"
    assert (await client.post(f"{API}/player-career/moments/0", headers=headers, json={"option": "shot"})).status_code == 409
    after = await player_career_service.play_moment(db_session, user, 1, "pass", False, rng=_Rng(0.0))
    assert after["pending"] is None  # all played → finalized
    db_session.expire_all()
    row = await db_session.get(PlayerCareerSeason, season_id)
    me = row.state["my_rounds"]["0"]
    assert me["goals"] == base_goals + 1 and me["assists"] >= 1 and me["own"] == base_own + 2
    assert me["rating"] is not None and me["headline"]
    entry = next(e for e in row.state["results"][0] if 0 in (e["home"], e["away"]))
    assert (entry["hs"] if entry["home"] == 0 else entry["as"]) == me["own"]


async def test_overdue_moments_are_played_by_the_coach(client, db_session, bot_token):
    user_id, headers, _ = await _signed(client, db_session, bot_token, 891002, position="CB")
    season_id, row = await _first_round_pending(client, db_session, headers, user_id)
    assert row.state["pending"]["moments"][0]["kind"] == "defense"
    deadline = datetime.fromisoformat(row.state["pending"]["deadline"])
    await player_career_service.resolve_due(db_session, season_id, now=deadline + timedelta(seconds=1))
    db_session.expire_all()
    row = await db_session.get(PlayerCareerSeason, season_id)
    assert "pending" not in row.state or row.state["pending"]["round"] != 0
    assert all(m["auto"] for m in row.state["my_rounds"]["0"]["moments"])


def test_moment_odds_and_totals():
    class Cfg:
        player_career_moment_hit_pct = 18
    stats = {"attack": 80, "defense": 50}
    assert moments.chance("attack", "shot", stats, True, Cfg) == moments.chance("attack", "shot", stats, False, Cfg) + 18
    assert moments.chance("defense", "block", {"attack": 50, "defense": 20}, False, Cfg) >= 10
    done = [
        {"kind": "attack", "choice": "dribble", "status": "done", "success": True},
        {"kind": "defense", "choice": "tackle", "status": "done", "success": False},
    ]
    t = moments.totals(done)
    assert t["own"] == 1 and t["goals"] == 1 and t["opp"] == 1


async def test_role_trust_and_captain(db_session):
    config = await get_config(db_session)
    mp = MyPlayer(trust=50)
    assert life.role_of(mp, 60, 70, config) == "bench"
    mp.trust = config.player_career_trust_starter
    assert life.role_of(mp, 60, 70, config) == "starter"
    mp.trust = config.player_career_trust_captain
    assert life.role_of(mp, 72, 70, config) == "captain"
    mp.trust = 10
    assert life.role_of(mp, 90, 70, config) == "bench"  # a coach who lost faith
    life.move_trust(mp, 500)
    assert mp.trust == 100
    assert life.trust_after_match(7.8) > 0 > life.trust_after_match(5.5)


async def test_injury_and_paid_healing(client, db_session, bot_token):
    config = await get_config(db_session)
    assert life.injury_roll(100, config, _Rng(0.0)) == 0
    assert 1 <= life.injury_roll(0, config, _Rng(0.0)) <= 3
    user_id, headers, _ = await _signed(client, db_session, bot_token, 891003)
    mp = await my_player_service.get_my_player(db_session, user_id)
    mp.injury_rounds = 2
    user = await db_session.get(User, user_id)
    user.balance = config.player_career_heal_coins
    await db_session.commit()
    assert (await client.get(f"{API}/player-career", headers=headers)).json()["injury_rounds"] == 2
    resp = await client.post(f"{API}/player-career/shop/heal", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["injury_rounds"] == 0 and resp.json()["balance"] == 0
    assert (await client.post(f"{API}/player-career/shop/heal", headers=headers)).status_code == 409  # healthy


async def test_story_event_choice_applies_effects(client, db_session, bot_token):
    user_id, headers, _ = await _signed(client, db_session, bot_token, 891004)
    season = (await client.post(f"{API}/player-career/seasons", headers=headers)).json()["season"]
    db_session.expire_all()
    row = await db_session.get(PlayerCareerSeason, season["id"])
    state = dict(row.state)
    state["events"] = [{"id": 1, "code": "ad", "round": 0, "status": "open", "answer": None}]
    row.state = state
    await db_session.commit()
    view = (await client.get(f"{API}/player-career", headers=headers)).json()
    assert view["event"]["title"] == "Рекламный контракт"
    config = await get_config(db_session)
    balance = view["balance"]
    resp = await client.post(f"{API}/player-career/events/1", headers=headers, json={"choice": "sign"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["balance"] == balance + 3 * config.player_career_event_coins
    assert resp.json()["event"] is None
    assert (await client.post(f"{API}/player-career/events/1", headers=headers, json={"choice": "rest"})).status_code == 409


async def test_friends_league_with_derbies(client, db_session, bot_token):
    db_session.add(TrophyDefinition(code="player_career_friends_champion", name="Чемпион лиги друзей", is_active=True))
    await db_session.commit()
    a_id, a_headers, _ = await _signed(client, db_session, bot_token, 891005)
    b_id, b_headers, _ = await _signed(client, db_session, bot_token, 891006)
    db_session.add(Friendship(requester_id=a_id, addressee_id=b_id, user_low=min(a_id, b_id), user_high=max(a_id, b_id), status="accepted"))
    await db_session.commit()

    view = (await client.get(f"{API}/player-career/friends", headers=a_headers)).json()
    assert [f["user_id"] for f in view["friends"]] == [b_id] and view["can_create"]
    created = (await client.post(f"{API}/player-career/friends", headers=a_headers, json={"invite_ids": [b_id]})).json()
    league_id = created["league"]["id"]
    assert (await client.post(f"{API}/player-career/friends/{league_id}/start", headers=a_headers)).status_code == 409  # nobody joined
    invites = (await client.get(f"{API}/player-career/friends", headers=b_headers)).json()["invites"]
    assert invites[0]["id"] == league_id
    assert (await client.post(f"{API}/player-career/friends/{league_id}/respond", headers=b_headers, json={"accept": True})).status_code == 200
    started = (await client.post(f"{API}/player-career/friends/{league_id}/start", headers=a_headers)).json()
    league = started["league"]
    assert league["status"] == "active" and len(league["table"]) == 8
    assert sum(1 for r in league["rounds"] for m in r["matches"] if m["derby"]) == 1  # they meet once

    from app.services import player_career_friends

    assert await player_career_friends.resolve_league(db_session, league_id, now=datetime.now(timezone.utc) + timedelta(days=5)) == 7
    db_session.expire_all()
    row = await db_session.get(PlayerCareerFriendLeague, league_id)
    assert row.status == "finished" and len(row.state["derbies"]) == 1
    view = (await client.get(f"{API}/player-career/friends", headers=a_headers)).json()
    assert view["league"]["status"] == "finished" and view["league"]["h2h"]
    assert {p["matches"] for p in view["league"]["players"]} == {7}
    winner_team = view["league"]["table"][0]
    trophies = (await db_session.execute(select(UserTrophy))).scalars().all()
    assert bool(trophies) == winner_team["is_friend"]


async def test_weekly_tasks_rankings_and_daily_chest(client, db_session, bot_token):
    user_id, headers, _ = await _signed(client, db_session, bot_token, 891007)
    config = await get_config(db_session)
    now = datetime.now(timezone.utc)
    for _ in range(config.player_career_weekly_matches):
        await life.record_week(db_session, user_id, now, 1, 0, 7.5, False)
    await db_session.commit()
    view = (await client.get(f"{API}/player-career", headers=headers)).json()
    tasks = {t["code"]: t for t in view["weekly"]["tasks"]}
    assert tasks["goals"]["done"] and tasks["matches"]["done"] and tasks["rating"]["done"]
    balance = view["balance"]
    claimed = await client.post(f"{API}/player-career/weekly/goals/claim", headers=headers)
    assert claimed.status_code == 200 and claimed.json()["balance"] == balance + config.player_career_weekly_coins[0]
    assert (await client.post(f"{API}/player-career/weekly/goals/claim", headers=headers)).status_code == 409

    ranks = (await client.get(f"{API}/player-career/rankings", headers=headers)).json()
    assert ranks["scorers"][0]["is_me"] and ranks["scorers"][0]["value"] == config.player_career_weekly_matches

    assert view["chest"]["available"]
    chest = await client.post(f"{API}/player-career/chest", headers=headers)
    assert chest.status_code == 200, chest.text
    assert config.player_career_chest_coins_min <= chest.json()["coins"] <= config.player_career_chest_coins_max
    assert (await client.post(f"{API}/player-career/chest", headers=headers)).status_code == 409


async def test_hall_of_fame_after_a_season(client, db_session, bot_token):
    user_id, headers, club = await _signed(client, db_session, bot_token, 891008)
    season = (await client.post(f"{API}/player-career/seasons", headers=headers)).json()["season"]
    await player_career_service.resolve_due(db_session, season["id"], now=datetime.now(timezone.utc) + timedelta(days=8))
    record = (await db_session.execute(select(PlayerCareerClubRecord).where(PlayerCareerClubRecord.user_id == user_id))).scalar_one()
    assert record.seasons == 1 and record.club_key == club["key"]
    view = (await client.get(f"{API}/player-career", headers=headers)).json()
    assert view["legends"][0]["is_me"] and view["legends"][0]["seasons"] == 1
    mine = next(c for c in view["clubs"] if c["key"] == club["key"])
    assert mine["legend"]["seasons"] == 1


async def test_paid_extras_pro_agent_fast_season(client, db_session, bot_token, monkeypatch):
    from app.services import stars_payment_service
    from tests.test_gifts import INTERNAL_HEADERS, _deliver, _fake_invoice_link

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    user_id, headers, _ = await _signed(client, db_session, bot_token, 891009)
    config = await get_config(db_session)
    pro_stars, base_moments, fast_minutes = (
        config.player_career_pro_stars, config.player_career_moments, config.player_career_fast_round_minutes,
    )

    async def buy(code, arg=None, charge="c"):
        body = {"purchase": "career", "code": code, **({"position": arg} if arg else {})}
        resp = await client.post(f"{API}/my-player/stars-invoice", headers=headers, json=body)
        assert resp.status_code == 200, resp.text
        token, stars = resp.json()["payload_token"], resp.json()["stars_amount"]
        pre = await client.post("/api/v1/internal/stars-payments/pre-checkout", headers=INTERNAL_HEADERS,
                                json={"payload_token": token, "total_amount": stars})
        assert pre.json()["ok"] is True, pre.json()
        assert (await _deliver(client, token, 891009, f"{charge}-{code}", stars)).status_code == 200
        return stars

    assert await buy("pro") == pro_stars
    view = (await client.get(f"{API}/player-career", headers=headers)).json()
    assert view["shop"]["pro"] and view["player"]["pro"]
    mine = (await client.get(f"{API}/my-player", headers=headers)).json()
    assert "bg_pro" in mine["cosmetics"]["owned"]
    # Pro: one more key moment.
    _, row = await _first_round_pending(client, db_session, headers, user_id)
    assert len(row.state["pending"]["moments"]) == base_moments + 1
    await client.post(f"{API}/player-career/leave", headers=headers)

    # Switched off by default: not sold.
    off = await client.post(f"{API}/my-player/stars-invoice", headers=headers, json={"purchase": "career", "code": "fast"})
    assert off.status_code == 409
    cfg = await get_config(db_session)
    cfg.player_career_fast_season_enabled = True
    await db_session.commit()
    await buy("fast", charge="f")
    resp = await client.post(f"{API}/player-career/seasons", headers=headers, json={"fast": True})
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    fast = await db_session.get(PlayerCareerSeason, resp.json()["season"]["id"])
    times = [datetime.fromisoformat(t) for t in fast.state["schedule"][:2]]
    assert (times[1] - times[0]) == timedelta(minutes=fast_minutes)
    await client.post(f"{API}/player-career/leave", headers=headers)
    # Without a credit a fast season is refused.
    assert (await client.post(f"{API}/player-career/seasons", headers=headers, json={"fast": True})).status_code == 409

    await buy("agent", charge="a")
    mp = await my_player_service.get_my_player(db_session, user_id)
    assert mp.agent_credits == 1
    # Nothing to heal / nothing withdrawn: refused before payment.
    assert (await client.post(f"{API}/my-player/stars-invoice", headers=headers,
                              json={"purchase": "career", "code": "heal"})).status_code == 409
    assert (await client.post(f"{API}/my-player/stars-invoice", headers=headers,
                              json={"purchase": "career", "code": "save_offer", "position": "cc:1"})).status_code == 409


def test_headlines_keep_the_name_as_is():
    base = {"played": True, "goals": 0, "assists": 0, "rating": 6.8, "stops": 0}
    assert life.headline("Виктор", "Вега", "Витязь", 2, 1, {**base, "goals": 3}, "cel_siu").startswith("Виктор оформляет хет-трик и празднует")
    assert life.headline("Виктор", "Вега", "Витязь", 1, 2, {**base, "goals": 1}, None) == "Виктор забил, но победы нет: «Вега» — «Витязь» 1:2"
    assert life.headline("Виктор", "Вега", "Витязь", 1, 0, {**base, "stops": 2}, None).startswith("Виктор — стена!")
    assert life.headline("Виктор", "Вега", "Витязь", 0, 0, {"played": False, "injured": True}, None).startswith("Виктор лечит травму")
