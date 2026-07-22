from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.achievement import Achievement, UserAchievement
from app.models.enums import TransactionType
from app.models.user import User
from app.services.wallet_service import credit_coins


async def evaluate_and_award(db: AsyncSession, user: User, metric: str, value: int) -> list[Achievement]:
    """Awards any not-yet-claimed achievements for `metric` whose target is met.

    Intended to be called from within an already-open transaction (before the
    caller's final commit) so the reward stays atomic with the triggering action.
    """
    result = await db.execute(
        select(Achievement).where(Achievement.metric == metric, Achievement.target_value <= value)
    )
    achievements = result.scalars().all()
    awarded: list[Achievement] = []

    for achievement in achievements:
        existing = (
            await db.execute(
                select(UserAchievement).where(
                    UserAchievement.user_id == user.id, UserAchievement.achievement_id == achievement.id
                )
            )
        ).scalar_one_or_none()
        if existing and existing.reward_claimed:
            continue

        if existing is None:
            existing = UserAchievement(user_id=user.id, achievement_id=achievement.id, progress=value)
            db.add(existing)
            await db.flush()

        existing.progress = value
        existing.completed_at = datetime.now(timezone.utc)
        existing.reward_claimed = True
        db.add(existing)

        if achievement.reward_coins > 0:
            await credit_coins(
                db, user, achievement.reward_coins, TransactionType.achievement_reward,
                f"Достижение «{achievement.name}»", "achievement", achievement.id,
            )
        awarded.append(achievement)

    return awarded


async def list_with_progress(db: AsyncSession, user: User) -> list[dict]:
    achievements = (await db.execute(select(Achievement))).scalars().all()
    progress_rows = (
        await db.execute(select(UserAchievement).where(UserAchievement.user_id == user.id))
    ).scalars().all()
    progress_by_id = {p.achievement_id: p for p in progress_rows}

    out = []
    for ach in achievements:
        p = progress_by_id.get(ach.id)
        out.append(
            {
                "id": ach.id,
                "code": ach.code,
                "name": ach.name,
                "description": ach.description,
                "reward_coins": ach.reward_coins,
                "target_value": ach.target_value,
                "progress": p.progress if p else 0,
                "completed": bool(p and p.completed_at is not None),
            }
        )
    return out
