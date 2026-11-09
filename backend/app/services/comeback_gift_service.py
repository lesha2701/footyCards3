"""«Подарок за возвращение»: a player who was away for
GameConfig.comeback_gift_days+ gets coins and a pack on return. Checked once
a day per player (core/dependencies, after the streak moved), at most once
per comeback_gift_cooldown_days so returning every week doesn't farm it, and
shown as a popup until it's marked seen. New accounts have no last visit, so
they never qualify. The bot announces it: bot/services/comeback.py."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.comeback_gift import ComebackGift
from app.models.enums import CardSource, TransactionType
from app.models.pack import Pack
from app.models.user import User
from app.services import reward_bundle_service
from app.services.game_config_service import get_config
from app.services.reward_bundle_service import Bundle
from app.services.wallet_service import lock_user_for_update


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def check(db: AsyncSession, user: User, previous_seen_at: Optional[datetime]) -> None:
    """Grants the gift if this visit ends a long enough absence. Commits."""
    if previous_seen_at is None:
        return
    config = await get_config(db)
    now = datetime.now(timezone.utc)
    days_away = (now - _aware(previous_seen_at)).days
    if not config.comeback_gift_enabled or days_away < config.comeback_gift_days:
        return
    pack_id = None
    if config.comeback_gift_pack_slug:
        pack_id = (await db.execute(
            select(Pack.id).where(Pack.slug == config.comeback_gift_pack_slug)
        )).scalar_one_or_none()
    if not config.comeback_gift_coins and pack_id is None:
        return

    locked = await lock_user_for_update(db, user.id)
    # Several first requests of a visit race here: the row lock serializes
    # them and the winner's row puts the others inside the cooldown.
    last = (await db.execute(
        select(ComebackGift.granted_at).where(ComebackGift.user_id == locked.id)
        .order_by(ComebackGift.granted_at.desc()).limit(1)
    )).scalar_one_or_none()
    if last is not None and now - _aware(last) < timedelta(days=config.comeback_gift_cooldown_days):
        await db.rollback()
        return
    try:
        async with db.begin_nested():
            row = ComebackGift(user_id=locked.id, gift_date=now.date(), days_away=days_away, rewards={})
            db.add(row)
            await db.flush()
    except IntegrityError:
        await db.rollback()
        return
    granted = await reward_bundle_service.grant(
        db, locked, Bundle(coins=config.comeback_gift_coins, pack_id=pack_id),
        tx_type=TransactionType.achievement_reward, description="Подарок за возвращение",
        card_source=CardSource.task, idempotency_prefix=f"comeback-{row.id}", cosmetic_source="comeback",
    )
    row.rewards = granted.model_dump(mode="json")
    await db.commit()


async def unseen(db: AsyncSession, user: User) -> list[ComebackGift]:
    return list((await db.execute(
        select(ComebackGift).where(ComebackGift.user_id == user.id, ComebackGift.seen_at.is_(None))
        .order_by(ComebackGift.id)
    )).scalars().all())


async def mark_seen(db: AsyncSession, user: User, gift_id: int) -> None:
    row = await db.get(ComebackGift, gift_id)
    if row is None or row.user_id != user.id:
        raise NotFoundError("Подарок не найден")
    if row.seen_at is None:
        row.seen_at = datetime.now(timezone.utc)
        await db.commit()
