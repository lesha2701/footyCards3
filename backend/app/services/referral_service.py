"""Referrals. The relationship is recorded at registration
(core/dependencies._get_or_create_user, `users.referred_by_id`), the
referrer only gets a «друг присоединился» notice then. The friend counts —
both get their coins and the referrer's `referral_count` grows — once the
friend has really played: active on GameConfig.referral_active_days
different local days (user_daily_activity). A pack open is no signal any
more (free and «Путь дебютанта» packs cost nothing), so throwaway accounts
earn nothing.

Each counted friend may also pay a milestone of GameConfig.referral_milestones
(`[{"count": 3, "coins": …, "pack_id": …, "card_rarity": …, "badge_id": …,
"cosmetic_id": …}]`); `users.referral_milestone_paid` is the highest count
already paid, so every milestone is paid once, in order."""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_activity import UserDailyActivity
from app.models.enums import CardSource, NotificationType, TransactionType
from app.models.user import User
from app.services import notification_service, reward_bundle_service, task_service
from app.services.game_config_service import get_config
from app.services.reward_bundle_service import Bundle
from app.services.wallet_service import credit_coins, lock_user_for_update


def _n(value: int) -> str:
    return f"{value:,}".replace(",", " ")


async def notify_joined(db: AsyncSession, referrer: User, friend: User) -> None:
    """At registration: the friend is in, the reward comes after his N days."""
    config = await get_config(db)
    await notification_service.notify(
        db, referrer.id, NotificationType.referral_joined, "🤝 Друг присоединился!",
        f"{friend.full_display_name()} пришёл по твоей ссылке. Когда он поиграет {config.referral_active_days} "
        f"дн., тебе придёт {_n(config.referral_referrer_reward)} монет.",
    )


async def _active_days(db: AsyncSession, user_id: int) -> int:
    return int((await db.execute(
        select(func.count()).select_from(UserDailyActivity).where(UserDailyActivity.user_id == user_id)
    )).scalar_one())


async def check_friend(db: AsyncSession, user: User) -> Optional[int]:
    """Called once a day per user (core/dependencies, after the daily
    activity row is committed). Counts the friend when he qualifies;
    returns the friend's own bonus. Commits."""
    if user.referred_by_id is None or user.referral_reward_granted:
        return None
    config = await get_config(db)
    if await _active_days(db, user.id) < config.referral_active_days:
        return None
    # Both rows, ascending id — the canonical two-user lock order.
    first, second = sorted((user.id, user.referred_by_id))
    a = await lock_user_for_update(db, first)
    b = await lock_user_for_update(db, second)
    friend, referrer = (a, b) if a.id == user.id else (b, a)
    if friend.referral_reward_granted:
        await db.commit()
        return None
    friend.referral_reward_granted = True
    referrer.referral_count += 1
    db.add_all([friend, referrer])
    await task_service.evaluate_metric_progress(db, referrer, "referrals_count", referrer.referral_count)
    if config.referral_referred_reward > 0:
        await credit_coins(
            db, friend, config.referral_referred_reward, TransactionType.referral_reward,
            "Бонус за приглашение от друга",
            related_object_type="user", related_object_id=referrer.id,
        )
    # related_object_id = the friend: the weekly «Рефералов» board counts these.
    if config.referral_referrer_reward > 0:
        await credit_coins(
            db, referrer, config.referral_referrer_reward, TransactionType.referral_reward,
            f"Награда за приглашение друга: {friend.full_display_name()}",
            related_object_type="user", related_object_id=friend.id,
        )
    await notification_service.notify(
        db, referrer.id, NotificationType.referral_joined, "🤝 Друг засчитан!",
        f"{friend.full_display_name()} играет уже {config.referral_active_days} дн. — тебе начислено "
        f"{_n(config.referral_referrer_reward)} монет.",
    )
    await _pay_milestones(db, referrer, config)
    await db.commit()
    return config.referral_referred_reward


def milestones(config) -> list[dict]:
    return sorted((m for m in config.referral_milestones or [] if m.get("count")), key=lambda m: m["count"])


async def _pay_milestones(db: AsyncSession, referrer: User, config) -> None:
    for m in milestones(config):
        if referrer.referral_milestone_paid < m["count"] <= referrer.referral_count:
            bundle = Bundle(
                coins=m.get("coins") or 0, pack_id=m.get("pack_id"), card_rarity=m.get("card_rarity"),
                badge_id=m.get("badge_id"), cosmetic_id=m.get("cosmetic_id"),
            )
            if not bundle.is_empty():
                await reward_bundle_service.grant(
                    db, referrer, bundle, tx_type=TransactionType.referral_reward,
                    description=f"Награда за {m['count']} друзей",
                    card_source=CardSource.task, idempotency_prefix=f"referral-milestone-{m['count']}",
                    cosmetic_source="referral",
                )
            await notification_service.notify(
                db, referrer.id, NotificationType.referral_joined, f"🏆 {m['count']} друзей!",
                f"Ты пригласил уже {m['count']} друзей — награда начислена.",
            )
            referrer.referral_milestone_paid = m["count"]
    db.add(referrer)
