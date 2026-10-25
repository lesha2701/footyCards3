from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

import app.core.rate_limit as rate_limit_module
from app.models.enums import TransactionType
from app.models.game import GameSession
from app.models.game_config import GameConfig
from app.models.pack import StarsInvoice
from app.models.transaction import CoinTransaction
from app.models.weekly_top import WeeklyTopAward, WeeklyTopRun
from app.schemas.ranking import RankingMetric
from app.services import ranking_service, weekly_top_service
from app.services.club_league_service import week_bounds
from app.services.wallet_service import credit_coins
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/weekly-top"


@pytest.fixture(autouse=True)
async def _setup(db_session):
    rate_limit_module._hits.clear()
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    config.weekly_top_enabled = True
    config.weekly_top_size = 3
    config.weekly_top_rewards = [{"coins": 300}, {"coins": 200}, {"coins": 100}]
    config.weekly_top_metrics = ["kontra_rating", "games_week", "stars_week"]
    await db_session.commit()
    yield


async def _user(client, db_session, bot_token, telegram_id, kontra=1000):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    user.kontra_rating = kontra
    db_session.add(user)
    await db_session.commit()
    return headers, user


def _in_week(week, hours=12):
    start, _ = week_bounds(week)
    return start + timedelta(hours=hours)


async def test_settle_pays_each_ranking_once_and_shows_popups(client, db_session, bot_token):
    week = weekly_top_service.last_closed_week()
    h1, u1 = await _user(client, db_session, bot_token, 980001, kontra=1500)
    h2, u2 = await _user(client, db_session, bot_token, 980002, kontra=1200)
    _, u3 = await _user(client, db_session, bot_token, 980003, kontra=900)
    u1_id, u2_id = u1.id, u2.id
    # Games: u2 played three this week, u1 one; one of u1's is from the week before.
    for uid, n in ((u2_id, 3), (u1_id, 1)):
        for _ in range(n):
            db_session.add(GameSession(user_id=uid, game_type="memory", created_at=_in_week(week)))
    db_session.add(GameSession(user_id=u1_id, game_type="memory", created_at=_in_week(week, hours=-30)))
    db_session.add(StarsInvoice(user_id=u2_id, payload_token="wt-1", stars_amount=50, completed_at=_in_week(week)))
    db_session.add(StarsInvoice(user_id=u1_id, payload_token="wt-2", stars_amount=500, completed_at=None))  # never paid
    await db_session.commit()
    before = {uid: (await db_session.get(type(u1), uid)).balance for uid in (u1_id, u2_id)}

    paid = await weekly_top_service.settle(db_session, week)
    # Kontra: u1, u2 (u3 is below the 1000 every player starts with); games: u2, u1; Stars: u2.
    assert paid == 2 + 2 + 1
    assert await weekly_top_service.settle(db_session, week) == 0  # once per week

    db_session.expire_all()
    awards = (await db_session.execute(select(WeeklyTopAward).where(WeeklyTopAward.week_start == week))).scalars().all()
    by = {(a.metric, a.rank): a.user_id for a in awards}
    assert by[("kontra_rating", 1)] == u1_id and by[("kontra_rating", 2)] == u2_id
    assert by[("games_week", 1)] == u2_id and by[("games_week", 2)] == u1_id
    assert by[("stars_week", 1)] == u2_id and ("stars_week", 2) not in by
    # u2: 2nd Kontra (200) + 1st games (300) + 1st Stars (300).
    assert (await db_session.get(type(u1), u2_id)).balance == before[u2_id] + 800
    txs = (await db_session.execute(
        select(func.count()).select_from(CoinTransaction)
        .where(CoinTransaction.user_id == u2_id, CoinTransaction.type == TransactionType.weekly_top_reward)
    )).scalar_one()
    assert txs == 3

    popups = (await client.get(f"{API}/awards", headers=h2)).json()
    assert sorted((p["metric"], p["rank"]) for p in popups) == [("games_week", 1), ("kontra_rating", 2), ("stars_week", 1)]
    assert [p["rank"] for p in popups] == [1, 1, 2]  # best places first
    assert all(p["metric_label"] and p["coins"] > 0 for p in popups)
    seen = await client.post(f"{API}/awards/seen", headers=h2, json={"ids": [p["id"] for p in popups[:2]]})
    assert seen.json()["seen"] == 2
    assert len((await client.get(f"{API}/awards", headers=h2)).json()) == 1
    # Someone else's award can't be marked.
    assert (await client.post(f"{API}/awards/seen", headers=h1, json={"ids": [popups[2]["id"]]})).json()["seen"] == 0

    # «Зал славы»: last week's podium of a ranking; empty for one never paid.
    hall = (await client.get(f"{API}/hall", headers=h1, params={"metric": "kontra_rating"})).json()
    assert hall["week_start"] == week.isoformat()
    assert [(w["rank"], w["user_id"], w["value"]) for w in hall["winners"]] == [(1, u1_id, 1500), (2, u2_id, 1200)]
    empty = (await client.get(f"{API}/hall", headers=h1, params={"metric": "cards_count"})).json()
    assert empty == {"week_start": None, "winners": []}


async def test_disabled_pays_nothing(client, db_session, bot_token):
    await _user(client, db_session, bot_token, 980010, kontra=1500)
    config = await db_session.get(GameConfig, 1)
    config.weekly_top_enabled = False
    await db_session.commit()
    week = weekly_top_service.last_closed_week()
    assert await weekly_top_service.settle(db_session, week) == 0
    assert await db_session.get(WeeklyTopRun, week) is None


async def test_lazy_settlement_on_the_awards_call(client, db_session, bot_token):
    headers, user = await _user(client, db_session, bot_token, 980020, kontra=5000)
    awards = (await client.get(f"{API}/awards", headers=headers)).json()
    assert any(a["metric"] == "kontra_rating" and a["rank"] == 1 for a in awards)
    assert await db_session.get(WeeklyTopRun, weekly_top_service.last_closed_week()) is not None


async def test_referrals_week_counts_rewarded_friends_only(client, db_session, bot_token):
    _, referrer = await _user(client, db_session, bot_token, 980030)
    _, friend = await _user(client, db_session, bot_token, 980031)
    _, stranger = await _user(client, db_session, bot_token, 980032)
    friend.referred_by_id = referrer.id
    db_session.add(friend)
    await credit_coins(db_session, referrer, 100, TransactionType.referral_reward, "friend",
                       related_object_type="user", related_object_id=friend.id)
    await credit_coins(db_session, referrer, 100, TransactionType.referral_reward, "not a referral",
                       related_object_type="user", related_object_id=stranger.id)
    await db_session.commit()
    rows = await ranking_service.top_rows(db_session, RankingMetric.referrals_week, 10)
    assert [(u.id, v) for u, v in rows] == [(referrer.id, 1)]


async def test_info_and_admin_ladder(client, db_session, bot_token):
    headers, _ = await _user(client, db_session, bot_token, 980040)
    session = await client.post("/api/v1/auth/session", headers=telegram_headers(999000001, bot_token))
    admin_headers = {"Authorization": f"Bearer {session.json()['admin_token']}"}
    info = (await client.get(f"{API}/info", headers=headers)).json()
    assert info["size"] == 3 and [p["coins"] for p in info["places"]] == [300, 200, 100]
    assert datetime.fromisoformat(info["ends_at"]) > datetime.now(timezone.utc)

    bad = await client.put("/api/v1/admin/games/config", headers=admin_headers,
                             json={"weekly_top_rewards": [{"coins": 10, "pack_id": 987654}]})
    assert bad.status_code == 409
    ok = await client.put("/api/v1/admin/games/config", headers=admin_headers,
                            json={"weekly_top_rewards": [{"coins": 999}], "weekly_top_metrics": ["kontra_rating", "nope"]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["weekly_top_rewards"][0]["coins"] == 999 and ok.json()["weekly_top_metrics"] == ["kontra_rating"]
