"""The Mini App opens with ~25 parallel requests. On a player's first visit
of the day only one of them may run the daily branch of
`_get_or_create_user` (streak, activity row, loyalty checks); the rest skip
it without waiting on the user row. Real Postgres (real_pg): SQLite has no
row locks."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.dependencies import _get_or_create_user
from app.core.security import TelegramUser
from app.core.timeutil import local_today
from app.models.user import User
from app.models.user_activity import UserDailyActivity


async def test_parallel_first_requests_of_the_day_count_the_day_once(real_pg):
    telegram_id = int(uuid.uuid4().int % 10**12)
    async with real_pg() as s:
        user = User(
            telegram_id=telegram_id, first_name="Day", balance=0, daily_login_streak=4,
            last_seen_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        s.add(user)
        await s.commit()
        user_id = user.id

    tg_user = TelegramUser(id=telegram_id, first_name="Day")

    async def one_request():
        async with real_pg() as s:
            seen = await _get_or_create_user(s, tg_user)
            return seen.daily_login_streak

    await asyncio.gather(*(one_request() for _ in range(12)))
    # Whichever request skipped the claim, the day is counted once.
    async with real_pg() as s:
        user = await s.get(User, user_id)
        assert user.daily_login_streak == 5
        assert local_today(user.last_seen_at) == local_today()
        days = (await s.execute(
            select(func.count()).select_from(UserDailyActivity).where(UserDailyActivity.user_id == user_id)
        )).scalar_one()
        assert days == 1

    # A later request the same day changes nothing.
    async with real_pg() as s:
        assert (await _get_or_create_user(s, tg_user)).daily_login_streak == 5
