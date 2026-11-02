from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import select

from app.models.club import Club
from app.models.club_budget import ClubBudgetTransaction
from app.models.club_league import ClubLeagueResult, ClubLeagueWeek
from app.models.enums import ClubBudgetTransactionType, GameSessionStatus, NotificationType, Position
from app.models.game import GameSession
from app.models.notification import Notification
from app.models.pack import PackOpening
from app.services import club_league_service
from app.services.game_config_service import get_config
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """create_club seeds a starting squad — same seeding as test_clubs.py."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _make_club(client, db_session, bot_token, telegram_id, name):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    return resp.json()["id"], await get_user_by_telegram_id(db_session, telegram_id), headers


async def _join(client, db_session, bot_token, club_id, telegram_id):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    assert (await client.post(f"/api/v1/clubs/{club_id}/join", headers=headers)).status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


def _games(db_session, user_id, count, when=None):
    when = when or datetime.now(timezone.utc)
    for _ in range(count):
        db_session.add(GameSession(user_id=user_id, game_type="memory_sequence", status=GameSessionStatus.won, created_at=when))


async def _paid_pack(db_session, user_id, count):
    pack = await create_pack(db_session, slug=f"league-{user_id}", price=100, card_count=1, probabilities={"common": 1.0})
    for i in range(count):
        db_session.add(PackOpening(user_id=user_id, pack_id=pack.id, price_paid=100, created_at=datetime.now(timezone.utc)))
    # A free/bonus opening never scores.
    db_session.add(PackOpening(user_id=user_id, pack_id=pack.id, price_paid=0, created_at=datetime.now(timezone.utc)))


async def test_league_table_ranks_clubs_by_member_activity(client, db_session, bot_token):
    club_a, captain_a, headers_a = await _make_club(client, db_session, bot_token, 880001, "Лига А")
    member_a = await _join(client, db_session, bot_token, club_a, 880002)
    club_b, captain_b, _ = await _make_club(client, db_session, bot_token, 880003, "Лига Б")

    _games(db_session, captain_a.id, 3)          # 3 × 2 = 6
    await _paid_pack(db_session, member_a.id, 2)  # 2 × 5 = 10
    _games(db_session, captain_b.id, 4)          # 4 × 2 = 8
    # In-progress sessions and activity from before joining do not count.
    db_session.add(GameSession(user_id=captain_b.id, game_type="memory_sequence", created_at=datetime.now(timezone.utc)))
    _games(db_session, member_a.id, 5, when=datetime.now(timezone.utc) - timedelta(hours=1))
    await db_session.commit()

    resp = await client.get("/api/v1/clubs/league", headers=headers_a)
    assert resp.status_code == 200
    body = resp.json()
    assert [(r["club_id"], r["points"], r["rank"]) for r in body["table"]] == [(club_a, 16, 1), (club_b, 8, 2)]
    assert body["my_row"]["club_id"] == club_a
    assert body["table"][0]["reward"] == body["rewards"][0]
    members = {m["user_id"]: m for m in body["members"]}
    assert members[member_a.id]["packs"] == 2 and members[member_a.id]["games"] == 0
    assert members[captain_a.id]["points"] == 6


async def test_member_weekly_cap(client, db_session, bot_token):
    club_id, captain, headers = await _make_club(client, db_session, bot_token, 880011, "Лига кап")
    config = await get_config(db_session)
    config.club_league_member_weekly_cap = 10
    db_session.add(config)
    _games(db_session, captain.id, 50)
    await db_session.commit()

    body = (await client.get("/api/v1/clubs/league", headers=headers)).json()
    assert body["my_row"]["points"] == 10
    assert body["members"][0]["games"] == 50


async def test_first_settlement_is_bootstrap_and_pays_nothing(db_session):
    assert await club_league_service.settle_due(db_session) == 0
    weeks = (await db_session.execute(select(ClubLeagueWeek))).scalars().all()
    assert len(weeks) == 1 and weeks[0].is_bootstrap
    # Same week again: no-op.
    assert await club_league_service.settle_due(db_session) == 0
    assert len((await db_session.execute(select(ClubLeagueWeek))).scalars().all()) == 1


async def test_settlement_pays_club_budgets_once(client, db_session, bot_token):
    club_a, captain_a, headers_a = await _make_club(client, db_session, bot_token, 880021, "Итоги А")
    member_a = await _join(client, db_session, bot_token, club_a, 880022)
    club_b, captain_b, _ = await _make_club(client, db_session, bot_token, 880023, "Итоги Б")
    _games(db_session, captain_a.id, 5)
    _games(db_session, captain_b.id, 2)
    config = await get_config(db_session)
    config.club_league_rewards = [700, 300]
    db_session.add(config)
    this_week = club_league_service.week_start_for()
    db_session.add(ClubLeagueWeek(week_start=this_week - timedelta(days=14), is_bootstrap=True))
    await db_session.commit()

    budget_a = (await db_session.get(Club, club_a)).budget
    budget_b = (await db_session.get(Club, club_b)).budget
    next_week = datetime.now(timezone.utc) + timedelta(days=7)
    assert await club_league_service.settle_due(db_session, now=next_week) == 2
    assert await club_league_service.settle_due(db_session, now=next_week) == 0

    assert await db_session.scalar(select(Club.budget).where(Club.id == club_a)) == budget_a + 700
    assert await db_session.scalar(select(Club.budget).where(Club.id == club_b)) == budget_b + 300
    results = (await db_session.execute(select(ClubLeagueResult).order_by(ClubLeagueResult.rank))).scalars().all()
    assert [(r.club_id, r.rank, r.points, r.reward) for r in results] == [(club_a, 1, 10, 700), (club_b, 2, 4, 300)]
    txs = (
        await db_session.execute(
            select(ClubBudgetTransaction).where(ClubBudgetTransaction.type == ClubBudgetTransactionType.league_reward)
        )
    ).scalars().all()
    assert sorted(t.amount for t in txs) == [300, 700]
    notified = (
        await db_session.execute(select(Notification.user_id).where(Notification.type == NotificationType.club_league_reward))
    ).scalars().all()
    assert sorted(notified) == sorted([captain_a.id, member_a.id, captain_b.id])


async def test_league_disabled_does_not_settle(db_session):
    config = await get_config(db_session)
    config.club_league_enabled = False
    db_session.add(config)
    await db_session.commit()
    assert await club_league_service.settle_due(db_session) == 0
    assert (await db_session.execute(select(ClubLeagueWeek))).scalars().first() is None


async def test_internal_settle_endpoint_requires_secret(client):
    resp = await client.post("/api/v1/internal/clubs/league/settle")
    assert resp.status_code in (401, 403)


async def test_shown_table_is_cached_for_a_minute(db_session, monkeypatch):
    """The «Лига клубов» screen reuses the running week's table for
    TABLE_CACHE_S instead of recomputing every club's activity per open."""
    from app.services import club_league_service as svc
    from app.services.game_config_service import get_config

    calls = []

    async def fake(db, week, config, division=None):
        calls.append(division)
        return []

    monkeypatch.setattr(svc, "compute_table", fake)
    config = await get_config(db_session)
    week = svc.week_start_for()
    await svc._shown_table(db_session, week, config, 0)
    await svc._shown_table(db_session, week, config, 0)
    await svc._shown_table(db_session, week, config, 1)
    assert calls == [0, 1]
    monkeypatch.setattr(svc, "TABLE_CACHE_S", 0.0)
    await svc._shown_table(db_session, week, config, 0)
    assert calls == [0, 1, 0]
