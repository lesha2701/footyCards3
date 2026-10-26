"""Keepsakes for days in a row in the game (users.daily_login_streak):
GameConfig.streak_rewards `[{"days": 100, "coins": …, "pack_id": …,
"card_rarity": …, "badge_id": …, "cosmetic_id": …}]`. Checked once a day
per player (core/dependencies, after the streak moved); every milestone is
granted once (streak_rewards unique on user + days) and shown as a popup
on the next app open until it's marked seen."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.enums import CardSource, NotificationType, TransactionType
from app.models.streak_reward import StreakReward
from app.models.user import User
from app.services import notification_service, reward_bundle_service
from app.services.game_config_service import get_config
from app.services.reward_bundle_service import Bundle
from app.services.wallet_service import lock_user_for_update


def milestones(config) -> list[dict]:
    return sorted((m for m in config.streak_rewards or [] if m.get("days")), key=lambda m: m["days"])


async def check(db: AsyncSession, user: User) -> None:
    """Grants every reached milestone not granted yet. Commits."""
    config = await get_config(db)
    reached = [m for m in milestones(config) if user.daily_login_streak >= m["days"]]
    if not reached:
        return
    have = set((await db.execute(
        select(StreakReward.days).where(StreakReward.user_id == user.id)
    )).scalars().all())
    for m in reached:
        if m["days"] in have:
            continue
        locked = await lock_user_for_update(db, user.id)
        try:
            async with db.begin_nested():
                row = StreakReward(user_id=locked.id, days=m["days"], rewards={})
                db.add(row)
                await db.flush()
        except IntegrityError:
            continue  # a concurrent request granted it
        granted = await reward_bundle_service.grant(
            db, locked, Bundle(
                coins=m.get("coins") or 0, pack_id=m.get("pack_id"), card_rarity=m.get("card_rarity"),
                badge_id=m.get("badge_id"), cosmetic_id=m.get("cosmetic_id"),
            ),
            tx_type=TransactionType.achievement_reward,
            description=f"{m['days']} дней подряд в VICTOR FC", card_source=CardSource.task,
            idempotency_prefix=f"streak-{m['days']}", cosmetic_source="streak",
        )
        row.rewards = granted.model_dump(mode="json")
        await notification_service.notify(
            db, locked.id, NotificationType.admin_message, f"🎖️ {m['days']} дней подряд!",
            f"Ты с нами {m['days']} дней подряд — памятный подарок уже у тебя.",
        )
    await db.commit()


async def unseen(db: AsyncSession, user: User) -> list[StreakReward]:
    return list((await db.execute(
        select(StreakReward).where(StreakReward.user_id == user.id, StreakReward.seen_at.is_(None))
        .order_by(StreakReward.days)
    )).scalars().all())


async def mark_seen(db: AsyncSession, user: User, reward_id: int) -> None:
    row = await db.get(StreakReward, reward_id)
    if row is None or row.user_id != user.id:
        raise NotFoundError("Награда не найдена")
    if row.seen_at is None:
        row.seen_at = datetime.now(timezone.utc)
        await db.commit()
