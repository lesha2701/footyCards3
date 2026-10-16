"""Race-sensitive monetization paths on real Postgres (row locks + unique
constraints). SQLite ignores SELECT ... FOR UPDATE, so these use the
`real_pg` fixture (tests/conftest.py); every row a test creates is deleted
on teardown."""
import asyncio
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.models.daily_reward import DailyReward
from app.models.monetization import ClubSubscription, Season, SeasonClaim, SeasonLevel, SeasonProgress
from app.models.pack import StarsInvoice
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.schemas.stars import StarsPaymentDeliverIn
from app.services import club_pass_service, daily_reward_service, season_pass_service, stars_receipt_service

TODAY = date(2026, 10, 16)


@pytest.fixture(autouse=True)
def _fresh_schema(monkeypatch):
    # The PG database is migrated by alembic and must not be dropped.
    monkeypatch.setattr(daily_reward_service, "local_today", lambda: TODAY)
    monkeypatch.setattr(club_pass_service, "local_today", lambda: TODAY)
    yield


async def _user(pg, balance=10_000) -> int:
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="Mon", balance=balance)
        s.add(user)
        await s.commit()
        return user.id


async def _run(pg, fn, *args):
    async with pg() as s:
        user = await s.get(User, args[0])
        try:
            return await fn(s, user, *args[1:])
        except AppError as exc:
            return exc


async def test_concurrent_calendar_claims_grant_once(real_pg):
    uid = await _user(real_pg)
    results = await asyncio.gather(*(_run(real_pg, daily_reward_service.claim_daily_reward, uid) for _ in range(4)))
    assert sum(not isinstance(r, AppError) for r in results) == 1
    async with real_pg() as s:
        rows = (await s.execute(select(func.count(DailyReward.id)).where(DailyReward.user_id == uid))).scalar_one()
        assert rows == 1


async def test_concurrent_catch_ups_respect_the_monthly_limit(real_pg):
    uid = await _user(real_pg)
    async with real_pg() as s:
        for n in range(1, 5):  # 4 of 5 catch-ups already used
            s.add(DailyReward(user_id=uid, reward_date=date(2026, 10, n), streak_day=n, claim_method="coins"))
        await s.commit()
    days = [date(2026, 10, n) for n in (6, 7, 8)]
    results = await asyncio.gather(*(_run(real_pg, daily_reward_service.catch_up_with_coins, uid, d) for d in days))
    assert sum(not isinstance(r, AppError) for r in results) == 1
    async with real_pg() as s:
        paid = (await s.execute(select(func.count(CoinTransaction.id)).where(
            CoinTransaction.user_id == uid, CoinTransaction.amount < 0,
        ))).scalar_one()
        assert paid == 1


async def test_concurrent_club_pass_daily_bonus_once(real_pg):
    uid = await _user(real_pg)
    async with real_pg() as s:
        s.add(ClubSubscription(user_id=uid, expires_at=datetime.now(timezone.utc) + timedelta(days=5)))
        await s.commit()
    results = await asyncio.gather(*(_run(real_pg, club_pass_service.claim_daily, uid) for _ in range(4)))
    assert sum(not isinstance(r, AppError) for r in results) == 1


async def test_redelivered_subscription_renewal_extends_once(real_pg):
    uid = await _user(real_pg)
    token = secrets.token_urlsafe(16)
    async with real_pg() as s:
        tg_id = (await s.get(User, uid)).telegram_id
        s.add(StarsInvoice(user_id=uid, payload_token=token, stars_amount=199, shop_product="club_pass"))
        await s.commit()

    def payload(charge):
        return StarsPaymentDeliverIn(payload_token=token, telegram_user_id=tg_id,
                                     telegram_payment_charge_id=charge, total_amount=199)

    async with real_pg() as s:
        await stars_receipt_service.deliver_with_receipt(s, payload(f"first-{uuid.uuid4().hex}"))
    async with real_pg() as s:
        first_end = (await s.execute(select(ClubSubscription).where(ClubSubscription.user_id == uid))).scalar_one().expires_at

    renewal = payload(f"renew-{uuid.uuid4().hex}")

    async def deliver():
        async with real_pg() as s:
            try:
                return await stars_receipt_service.deliver_with_receipt(s, renewal)
            except AppError as exc:
                return exc

    await asyncio.gather(*(deliver() for _ in range(4)))
    async with real_pg() as s:
        sub = (await s.execute(select(ClubSubscription).where(ClubSubscription.user_id == uid))).scalar_one()
        assert sub.expires_at - first_end == timedelta(days=30)
        assert sub.payments == 2
        renewals = (await s.execute(select(func.count(StarsInvoice.id)).where(
            StarsInvoice.user_id == uid, StarsInvoice.shop_product == "club_pass_renewal",
        ))).scalar_one()
        assert renewals == 1


async def test_concurrent_season_claims_grant_once(real_pg):
    uid = await _user(real_pg)
    now = datetime.now(timezone.utc)
    async with real_pg() as s:
        # Other test runs may leave no season; make ours the newest active one.
        season = Season(name="PG", starts_at=now - timedelta(minutes=1), ends_at=now + timedelta(days=1))
        s.add(season)
        await s.flush()
        s.add(SeasonLevel(season_id=season.id, level=1, xp_required=0, free_coins=100))
        s.add(SeasonProgress(user_id=uid, season_id=season.id, xp=5))
        await s.commit()
    results = await asyncio.gather(*(_run(real_pg, season_pass_service.claim, uid, 1, "free") for _ in range(4)))
    assert sum(not isinstance(r, AppError) for r in results) == 1
    async with real_pg() as s:
        assert (await s.execute(select(func.count(SeasonClaim.id)).where(SeasonClaim.user_id == uid))).scalar_one() == 1
        assert (await s.get(User, uid)).balance == 10_100
