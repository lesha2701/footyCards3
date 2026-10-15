from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_activity import UserDailyActivity


async def record_daily_activity(db: AsyncSession, user_id: int, day: date) -> None:
    """Mark `user_id` as active on local `day` (idempotent).

    Called on the user's first authenticated request of a day. A brand-new
    user's first app open fires many requests at once, so two can race to
    insert the same (user_id, day): the composite primary key turns the loser
    into a no-op inside its own SAVEPOINT instead of failing the request.
    The caller commits."""
    if await db.get(UserDailyActivity, (user_id, day)) is not None:
        return
    try:
        async with db.begin_nested():
            db.add(UserDailyActivity(user_id=user_id, day=day))
            await db.flush()
    except IntegrityError:
        pass
