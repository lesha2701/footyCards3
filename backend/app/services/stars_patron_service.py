"""Thanks to the players who support the game with Telegram Stars.

- «Покровитель недели»: once a week (lazily, from the first visit of anyone
  after Monday's local midnight — core/dependencies) the previous ISO week's
  top Stars buyers are settled. #1 gets the trophy, a card and a personal
  letter; the next places get a letter and coins. One settlement per week:
  the place-0 marker row of stars_patron_awards is unique.
- «Преторианец»: a player whose delivered purchases reach
  GameConfig.stars_praetorian_threshold Stars gets the badge (worn at once
  if he wears none) and the trophy, with a letter. Checked right after a
  delivered payment and once a day on login, so earlier buyers get it too.

Numbers live on GameConfig (stars_patron_*). Notifications go out through the
bot like every other one.
"""
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import app_timezone, local_today
from app.models.enums import CardSource, NotificationType, TransactionType
from app.models.stars_patron import StarsPatronAward
from app.models.stars_payment_receipt import StarsPaymentReceipt
from app.models.trophy import TrophyDefinition, UserTrophy
from app.models.user import User
from app.services import reward_bundle_service
from app.services.game_config_service import get_config
from app.services.notification_service import notify
from app.services.reward_bundle_service import Bundle
from app.services.wallet_service import lock_user_for_update

logger = logging.getLogger(__name__)

WEEK_TROPHY = "stars_patron_week"
PRAETORIAN_TROPHY = "stars_praetorian"
# Notification.related_object_type of the letters: the bot sends them and
# the game shows them once as a popup (StarsPatronLetter).
LETTER_TYPE = "stars_patron"


def _n(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def week_bounds(today: date) -> tuple[date, datetime, datetime]:
    """The ISO week before the one `today` is in: its Monday and its UTC span."""
    monday = today - timedelta(days=today.weekday()) - timedelta(days=7)
    tz = app_timezone()
    start = datetime.combine(monday, time(), tz).astimezone(timezone.utc)
    end = datetime.combine(monday + timedelta(days=7), time(), tz).astimezone(timezone.utc)
    return monday, start, end


async def _trophy(db: AsyncSession, code: str) -> Optional[TrophyDefinition]:
    return (await db.execute(
        select(TrophyDefinition).where(TrophyDefinition.code == code, TrophyDefinition.is_active.is_(True))
    )).scalar_one_or_none()


async def settle_last_week(db: AsyncSession) -> bool:
    """Settles the previous week once. True when this call did it. Commits."""
    config = await get_config(db)
    if not config.stars_patron_enabled:
        return False
    monday, start, end = week_bounds(local_today())
    done = (await db.execute(
        select(StarsPatronAward.id).where(StarsPatronAward.week_start == monday, StarsPatronAward.place == 0)
    )).first()
    if done:
        return False

    top = (await db.execute(
        select(User.id, func.sum(StarsPaymentReceipt.total_amount).label("stars"))
        .join(User, User.telegram_id == StarsPaymentReceipt.telegram_user_id)
        .where(
            StarsPaymentReceipt.status == "delivered",
            StarsPaymentReceipt.delivered_at >= start, StarsPaymentReceipt.delivered_at < end,
            User.is_banned.is_(False),
        )
        .group_by(User.id)
        .having(func.sum(StarsPaymentReceipt.total_amount) >= max(1, config.stars_patron_week_min))
        .order_by(func.sum(StarsPaymentReceipt.total_amount).desc(), User.id)
        .limit(max(0, config.stars_patron_week_places))
    )).all()
    try:
        async with db.begin_nested():
            db.add(StarsPatronAward(week_start=monday, place=0, user_id=None, stars=sum(r.stars for r in top)))
            rows = [StarsPatronAward(week_start=monday, place=n, user_id=r.id, stars=r.stars) for n, r in enumerate(top, 1)]
            db.add_all(rows)
            await db.flush()
    except IntegrityError:
        await db.rollback()
        return False

    trophy = await _trophy(db, WEEK_TROPHY)
    for row in rows:
        user = await lock_user_for_update(db, row.user_id)
        bundle = (
            Bundle(card_rarity=config.stars_patron_week_card_rarity or None) if row.place == 1
            else Bundle(coins=config.stars_patron_week_coins)
        )
        granted = await reward_bundle_service.grant(
            db, user, bundle, tx_type=TransactionType.achievement_reward,
            description=f"Покровитель недели · {row.place} место", card_source=CardSource.task,
            idempotency_prefix=f"stars-patron-{row.id}", cosmetic_source="stars_patron",
        )
        parts = [f"карта {c.player.display_name}" for c in granted.cards]
        if granted.coins:
            parts.insert(0, f"+{_n(granted.coins)} монет")
        gift = ", ".join(parts)
        name = user.first_name or "Друг"
        if row.place == 1:
            if trophy is not None:
                db.add(UserTrophy(
                    user_id=user.id, trophy_definition_id=trophy.id,
                    message=f"Неделя с {monday:%d.%m}: {_n(row.stars)} ⭐ — больше всех. Спасибо!",
                ))
            title = "👑 Ты — Покровитель недели!"
            body = (
                f"{name}, на прошлой неделе ты поддержал VICTOR FC больше всех — {_n(row.stars)} ⭐.\n"
                "Это не просто покупки: благодаря тебе игра растёт, выходят новые режимы и карты. "
                "Мы это видим и очень ценим.\n\n"
                f"В твоей витрине — трофей «Покровитель недели»{'. Подарок: ' + gift if gift else ''}.\n"
                "Спасибо, что ты с нами!\n\n— команда VICTOR FC"
            )
        else:
            title = f"🙏 Спасибо! Ты {row.place}-й среди покровителей недели"
            present = f"\nНебольшой подарок от нас: {gift}." if gift else ""
            body = (
                f"{name}, на прошлой неделе ты поддержал VICTOR FC на {_n(row.stars)} ⭐ — "
                f"это {row.place}-е место среди всех игроков. Мы это ценим!{present}\n\n— команда VICTOR FC"
            )
        await notify(db, user.id, NotificationType.trophy_granted, title, body, related_object_type=LETTER_TYPE)
    await db.commit()
    return True


async def lifetime_stars(db: AsyncSession, telegram_id: int) -> int:
    return int((await db.execute(
        select(func.coalesce(func.sum(StarsPaymentReceipt.total_amount), 0))
        .where(StarsPaymentReceipt.telegram_user_id == telegram_id, StarsPaymentReceipt.status == "delivered")
    )).scalar_one())


async def check_praetorian(db: AsyncSession, user_id: int) -> bool:
    """Grants «Преторианец» once the threshold is reached. True when granted now. Commits."""
    config = await get_config(db)
    badge_id = config.stars_praetorian_badge_id
    if not config.stars_patron_enabled or badge_id is None or config.stars_praetorian_threshold <= 0:
        return False
    user = await db.get(User, user_id)
    if user is None:
        return False
    total = await lifetime_stars(db, user.telegram_id)
    if total < config.stars_praetorian_threshold:
        return False
    locked = await lock_user_for_update(db, user_id)
    from app.models.badge import UserBadge

    owned = (await db.execute(
        select(UserBadge.id).where(UserBadge.user_id == locked.id, UserBadge.badge_id == badge_id)
    )).first()
    if owned:
        await db.rollback()
        return False
    badge = await reward_bundle_service.grant_badge(db, locked, badge_id)
    if badge is None:
        await db.rollback()
        return False
    trophy = await _trophy(db, PRAETORIAN_TROPHY)
    if trophy is not None:
        db.add(UserTrophy(
            user_id=locked.id, trophy_definition_id=trophy.id,
            message=f"{_n(total)} ⭐ поддержки VICTOR FC. Ты — гвардия клуба.",
        ))
    await notify(
        db, locked.id, NotificationType.trophy_granted, f"{badge.icon} Ты — Преторианец VICTOR FC",
        f"{locked.first_name or 'Друг'}, ты поддержал игру на {_n(total)} ⭐. Так делают единицы — "
        "это личная гвардия VICTOR FC.\n\n"
        f"Теперь рядом с твоим именем значок «{badge.name}», а в витрине — трофей. "
        "Его нельзя купить в магазине — только заслужить.\n"
        "Огромное спасибо — без таких игроков, как ты, игры бы не было.\n\n— команда VICTOR FC",
        related_object_type=LETTER_TYPE,
    )
    await db.commit()
    return True


async def run_daily(db: AsyncSession, user: User) -> None:
    """The once-a-day login hook: settle last week if nobody did yet, and
    catch up the «Преторианец» of this player. Never fails the request."""
    user_id = user.id  # read now: a rollback below expires the instance
    for step in (lambda: settle_last_week(db), lambda: check_praetorian(db, user_id)):
        try:
            await step()
        except Exception:  # noqa: BLE001 — a thank-you must not break a login
            logger.exception("stars patron step failed")
            await db.rollback()



async def unseen_letters(db: AsyncSession, user: User) -> list:
    """The thank-you letters not shown in the game yet (also sent by the bot)."""
    from app.models.notification import Notification

    return list((await db.execute(
        select(Notification).where(
            Notification.user_id == user.id, Notification.related_object_type == LETTER_TYPE,
            Notification.is_read.is_(False),
        ).order_by(Notification.id)
    )).scalars().all())


async def mark_letter_seen(db: AsyncSession, user: User, letter_id: int) -> None:
    from app.core.exceptions import NotFoundError
    from app.models.notification import Notification

    row = await db.get(Notification, letter_id)
    if row is None or row.user_id != user.id or row.related_object_type != LETTER_TYPE:
        raise NotFoundError("Письмо не найдено")
    if not row.is_read:
        row.is_read = True
        await db.commit()
