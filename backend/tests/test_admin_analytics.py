from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models.blackjack import BlackjackMatch
from app.models.enums import GameSessionStatus, GameType, TransactionType
from app.models.game import GameSession
from app.models.pack import StarsInvoice
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.models.user_activity import UserDailyActivity
from app.services.admin_analytics_service import analytics_report
from app.services.admin_economy_service import economy_report
from tests.test_admin_packs import _admin_auth
from tests.utils import telegram_headers

API = "/api/v1"
TODAY = date(2026, 10, 10)


def at(day: date, hour: int = 12) -> datetime:
    """`hour` o'clock Moscow time on `day`, as UTC (Moscow is UTC+3)."""
    return datetime(day.year, day.month, day.day, hour - 3, tzinfo=timezone.utc)


async def _user(db, tg_id: int, registered: date) -> User:
    user = User(telegram_id=tg_id, username=f"an_{tg_id}", balance=0, created_at=at(registered))
    db.add(user)
    await db.flush()
    return user


async def _active(db, user: User, *days: date) -> None:
    for d in days:
        db.add(UserDailyActivity(user_id=user.id, day=d))
    await db.flush()


async def test_first_request_of_the_day_records_activity_once(client, db_session, bot_token):
    for _ in range(3):
        resp = await client.post(f"{API}/auth/session", headers=telegram_headers(850001, bot_token))
        assert resp.status_code == 200
    user = (await db_session.execute(select(User).where(User.telegram_id == 850001))).scalar_one()
    rows = (await db_session.execute(
        select(func.count()).select_from(UserDailyActivity).where(UserDailyActivity.user_id == user.id)
    )).scalar_one()
    assert rows == 1


async def test_retention_counts_exact_day_returns_and_leaves_unreached_days_empty(db_session):
    reg = TODAY - timedelta(days=8)
    a = await _user(db_session, 850101, reg)   # back on D1 and D7
    b = await _user(db_session, 850102, reg)   # back on D1 only
    c = await _user(db_session, 850103, reg)   # back on D2 — neither D1 nor D7
    late = await _user(db_session, 850104, TODAY - timedelta(days=2))  # D7 not reached yet
    await _active(db_session, a, reg, reg + timedelta(days=1), reg + timedelta(days=7))
    await _active(db_session, b, reg, reg + timedelta(days=1))
    await _active(db_session, c, reg, reg + timedelta(days=2))
    await _active(db_session, late, TODAY - timedelta(days=2), TODAY - timedelta(days=1))
    await db_session.commit()

    report = await analytics_report(db_session, 30, today=TODAY)
    cohorts = {c["date"]: c for c in report["retention"]["cohorts"]}
    first = cohorts[reg.isoformat()]
    assert first["size"] == 3
    assert first["d1"] == round(2 / 3, 3)
    assert first["d7"] == round(1 / 3, 3)
    assert first["d30"] is None
    later = cohorts[(TODAY - timedelta(days=2)).isoformat()]
    assert later["d1"] == 1.0 and later["d7"] is None

    summary = report["retention"]["summary"]
    assert summary["d1_eligible"] == 4
    assert summary["d1"] == 0.75
    assert summary["d7_eligible"] == 3


async def test_activity_counts_dau_wau_mau_and_registrations_in_local_days(db_session):
    u1 = await _user(db_session, 850201, TODAY - timedelta(days=40))
    u2 = await _user(db_session, 850202, TODAY)
    await _active(db_session, u1, TODAY, TODAY - timedelta(days=3), TODAY - timedelta(days=20))
    await _active(db_session, u2, TODAY)
    # Registered at 01:00 Moscow on TODAY = still the previous UTC day: must count as TODAY.
    u3 = User(telegram_id=850203, username="an_night", balance=0, created_at=at(TODAY, hour=4) - timedelta(hours=3))
    db_session.add(u3)
    await db_session.commit()

    activity = (await analytics_report(db_session, 7, today=TODAY))["activity"]
    assert activity["dau_today"] == 2
    assert activity["wau"] == 2
    assert activity["mau"] == 2
    assert activity["stickiness"] == 1.0
    assert len(activity["dau_by_day"]) == 7
    assert activity["dau_by_day"][-1] == {"date": TODAY.isoformat(), "count": 2}
    assert activity["dau_by_day"][-4]["count"] == 1
    regs = {d["date"]: d["count"] for d in activity["registrations_by_day"]}
    assert regs[TODAY.isoformat()] == 2


async def test_modes_count_games_and_distinct_players(db_session):
    u1 = await _user(db_session, 850301, TODAY - timedelta(days=1))
    u2 = await _user(db_session, 850302, TODAY - timedelta(days=1))
    for user in (u1, u1, u2):
        db_session.add(GameSession(user_id=user.id, game_type=GameType.memory_sequence,
                                   status=GameSessionStatus.won, created_at=at(TODAY)))
    db_session.add(GameSession(user_id=u2.id, game_type=GameType.club_penalty,
                               status=GameSessionStatus.won, created_at=at(TODAY)))
    db_session.add(GameSession(user_id=u2.id, game_type=GameType.club_sequence,
                               status=GameSessionStatus.won, created_at=at(TODAY)))
    db_session.add(BlackjackMatch(user_id=u1.id, entry_source="free", server_state={}, created_at=at(TODAY)))
    # Outside the window: must not count.
    db_session.add(GameSession(user_id=u1.id, game_type=GameType.memory_sequence,
                               status=GameSessionStatus.won, created_at=at(TODAY - timedelta(days=40))))
    await db_session.commit()

    modes = {m["label"]: m for m in (await analytics_report(db_session, 7, today=TODAY))["modes"]}
    assert modes["Memory Sequence"]["games"] == 3 and modes["Memory Sequence"]["players"] == 2
    # Two club game types share one label: games add up, the player is counted once.
    assert modes["Клубные мини-игры"]["games"] == 2 and modes["Клубные мини-игры"]["players"] == 1
    assert modes["21: Добавленное время"]["games"] == 1 and modes["21: Добавленное время"]["players"] == 1
    assert modes["Card Arena"]["games"] == 0


async def test_funnel_and_monetization(db_session):
    reg = TODAY - timedelta(days=3)
    payer = await _user(db_session, 850401, reg)
    player = await _user(db_session, 850402, reg)
    idle = await _user(db_session, 850403, reg)
    await _active(db_session, payer, reg, reg + timedelta(days=1))
    await _active(db_session, player, reg)
    await _active(db_session, idle, reg)
    db_session.add(GameSession(user_id=player.id, game_type=GameType.saboteur, status=GameSessionStatus.lost, created_at=at(reg)))
    db_session.add(BlackjackMatch(user_id=payer.id, entry_source="stars", server_state={}, created_at=at(reg)))
    db_session.add(StarsInvoice(user_id=payer.id, payload_token="an-1", stars_amount=10, is_blackjack_entry=True,
                                completed_at=at(reg + timedelta(days=1))))
    db_session.add(StarsInvoice(user_id=payer.id, payload_token="an-2", stars_amount=50, coins_amount=1000,
                                completed_at=at(TODAY)))
    db_session.add(StarsInvoice(user_id=idle.id, payload_token="an-3", stars_amount=99, coins_amount=5000))  # never paid
    await db_session.commit()

    report = await analytics_report(db_session, 7, today=TODAY)
    steps = {s["key"]: s for s in report["funnel"]["steps"]}
    assert report["funnel"]["cohort_size"] == 3
    assert steps["played"]["users"] == 2
    assert steps["returned"]["users"] == 1
    assert steps["paid"]["users"] == 1
    assert steps["paid"]["share"] == round(1 / 3, 3)

    money = report["monetization"]
    assert money["stars_total"] == 60 and money["purchases"] == 2 and money["payers"] == 1
    assert money["arppu"] == 60.0
    products = {p["product"]: p for p in money["by_product"]}
    assert products["21: Добавленное время"]["stars"] == 10
    assert products["Монеты"]["stars"] == 50
    assert sum(d["count"] for d in money["stars_by_day"]) == 60


async def test_economy_warns_when_coins_are_minted_much_faster_than_spent(db_session):
    user = await _user(db_session, 850501, TODAY - timedelta(days=5))
    db_session.add(CoinTransaction(user_id=user.id, amount=900, balance_before=0, balance_after=900,
                                   type=TransactionType.task_reward))
    db_session.add(CoinTransaction(user_id=user.id, amount=-100, balance_before=900, balance_after=800,
                                   type=TransactionType.pack_purchase))
    user.balance = 800
    await db_session.commit()

    report = await economy_report(db_session, 7)
    assert report["inflow_outflow_ratio"] == 9.0
    assert report["warning"] and "9.0" in report["warning"]
    assert report["coins_in_circulation"] >= 800


async def test_economy_has_no_warning_when_balanced(db_session):
    user = await _user(db_session, 850601, TODAY - timedelta(days=5))
    db_session.add(CoinTransaction(user_id=user.id, amount=100, balance_before=0, balance_after=100,
                                   type=TransactionType.task_reward))
    db_session.add(CoinTransaction(user_id=user.id, amount=-100, balance_before=100, balance_after=0,
                                   type=TransactionType.pack_purchase))
    await db_session.commit()
    assert (await economy_report(db_session, 7))["warning"] is None


async def test_analytics_endpoint_is_admin_only_and_returns_report(client, bot_token):
    resp = await client.get(f"{API}/admin/dashboard/analytics", headers=telegram_headers(850701, bot_token))
    assert resp.status_code in (401, 403)

    auth = await _admin_auth(client, bot_token)
    body = (await client.get(f"{API}/admin/dashboard/analytics?days=7", headers=auth)).json()
    assert body["days"] == 7
    assert len(body["activity"]["dau_by_day"]) == 7
    assert {s["key"] for s in body["funnel"]["steps"]} == {"registered", "opened_pack", "played", "returned", "paid"}
