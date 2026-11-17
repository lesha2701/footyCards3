"""Loyalty keepsakes and «Страховка серии».

- «Старожил»: the account is `oldtimer_days`+ days old and was active on
  `oldtimer_active_days`+ of them (user_daily_activity — a lower bound before
  migration 0150), not banned. It's checked on a visit, so "alive" is a given.
  Badge «Старожил» (green 100), the profile frame, a card of
  `oldtimer_card_rarity` and a pack (`oldtimer_pack_id`, if set).
- «Подарок старожилу»: every «Старожил» gets the anniversary pack once, on
  the first visit while the event runs (before the start its cards — a
  collection of the event — must not drop; whoever became an oldtimer
  earlier gets it at the start).
- «Первопроходец»: one of the first `pioneer_limit` registered players (by id,
  like the anniversary recap's player number). Badge and gold frame.
- «Центурион» backpay: the card for 100 days in a row lives in
  GameConfig.streak_rewards (player_id); whoever got the 100-day keepsake
  before it existed and owns no copy gets the card and the purple badge.
- «Страховка серии»: missing exactly one day breaks a streak of at least
  `streak_save_min_streak`; its length is kept for `streak_save_hours`, and
  buying it back (Stars, or once per `streak_save_free_period_days` free
  with the club pass) adds it to the streak that started again.

Every keepsake is one loyalty_rewards row (unique user + code) shown as a
popup until it's seen. Numbers and ids: GameConfig.loyalty_settings over
DEFAULTS (admin «Игры» → «Лояльность»)."""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.card import UserCard
from app.models.enums import CardSource, NotificationType, TransactionType
from app.models.loyalty import LoyaltyReward
from app.models.player import Player
from app.models.streak_reward import StreakReward
from app.models.user import User
from app.models.user_activity import UserDailyActivity
from app.services import notification_service, reward_bundle_service
from app.services.game_config_service import get_config
from app.services.reward_bundle_service import Bundle
from app.services.wallet_service import lock_user_for_update

logger = logging.getLogger(__name__)

OLDTIMER = "oldtimer"
OLDTIMER_GIFT = "oldtimer_gift"
PIONEER = "pioneer"
CENTURION = "centurion"
CENTURION_DAYS = 100

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "oldtimer_days": 100,
    "oldtimer_active_days": 50,
    "oldtimer_coins": 0,
    "oldtimer_card_rarity": "legendary",
    "oldtimer_pack_id": None,
    "oldtimer_badge_id": None,
    "oldtimer_cosmetic_id": None,
    "pioneer_limit": 100,
    "pioneer_badge_id": None,
    "pioneer_cosmetic_id": None,
    "centurion_player_id": None,
    "centurion_badge_id": None,
    "streak_save_enabled": True,
    "streak_save_min_streak": 7,
    "streak_save_hours": 24,
    "streak_save_stars": 50,
    "streak_save_free_period_days": 30,
}
INT_KEYS = (
    "oldtimer_days", "oldtimer_active_days", "oldtimer_coins", "pioneer_limit", "streak_save_min_streak",
    "streak_save_hours", "streak_save_stars", "streak_save_free_period_days",
)
ID_KEYS = (
    "oldtimer_pack_id", "oldtimer_badge_id", "oldtimer_cosmetic_id", "pioneer_badge_id", "pioneer_cosmetic_id",
    "centurion_player_id", "centurion_badge_id",
)
TITLES = {
    OLDTIMER: ("Старожил", "100 дней в VICTOR FC — спасибо, что ты с нами!"),
    OLDTIMER_GIFT: ("Подарок старожилу", "Юбилейный пак к 100 дням VICTOR FC — спасибо, что ты с нами!"),
    PIONEER: ("Первопроходец", "Ты один из первых игроков VICTOR FC."),
    CENTURION: ("Центурион", "100 дней подряд — эксклюзивная карта, которой нет в паках."),
}


def settings(config) -> dict[str, Any]:
    return {**DEFAULTS, **(config.loyalty_settings or {})}


def clean_settings(raw: dict) -> dict[str, Any]:
    """Admin input: known keys only, numbers in range."""
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in DEFAULTS:
            continue
        if key in ("enabled", "streak_save_enabled"):
            out[key] = bool(value)
        elif key in INT_KEYS:
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 1_000_000:
                raise ConflictError(f"Лояльность: {key} — целое число от 0")
            out[key] = value
        elif key in ID_KEYS:
            out[key] = int(value) if value else None
        elif key == "oldtimer_card_rarity":
            out[key] = value or None
    if out.get("streak_save_stars") == 0 and "streak_save_stars" in raw:
        raise ConflictError("Лояльность: цена страховки — хотя бы 1 ⭐")
    return out


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --- keepsakes ----------------------------------------------------------------------


async def _due(db: AsyncSession, user: User, s: dict, have: set[str]) -> list[tuple[str, Bundle]]:
    due: list[tuple[str, Bundle]] = []
    if user.is_banned:
        return due
    if PIONEER not in have and (s["pioneer_badge_id"] or s["pioneer_cosmetic_id"]):
        number = (await db.execute(select(func.count(User.id)).where(User.id <= user.id))).scalar_one()
        if number <= s["pioneer_limit"]:
            due.append((PIONEER, Bundle(badge_id=s["pioneer_badge_id"], cosmetic_id=s["pioneer_cosmetic_id"])))
    created = _aware(user.created_at)
    if OLDTIMER not in have and created and created <= _now() - timedelta(days=s["oldtimer_days"]):
        active = (await db.execute(
            select(func.count()).select_from(UserDailyActivity).where(UserDailyActivity.user_id == user.id)
        )).scalar_one()
        if active >= s["oldtimer_active_days"]:
            due.append((OLDTIMER, Bundle(
                coins=s["oldtimer_coins"], card_rarity=s["oldtimer_card_rarity"], pack_id=s["oldtimer_pack_id"] or None,
                badge_id=s["oldtimer_badge_id"], cosmetic_id=s["oldtimer_cosmetic_id"],
            )))
    is_oldtimer = OLDTIMER in have or any(code == OLDTIMER for code, _ in due)
    if is_oldtimer and OLDTIMER_GIFT not in have:
        from app.services import anniversary_service

        config = await get_config(db)
        pack_id = (config.anniversary_settings or {}).get("pack_id")
        if pack_id and anniversary_service.is_active(config):
            due.append((OLDTIMER_GIFT, Bundle(pack_id=pack_id)))
    player_id = s["centurion_player_id"]
    if CENTURION not in have and player_id:
        reached = (await db.execute(
            select(StreakReward.id).where(StreakReward.user_id == user.id, StreakReward.days == CENTURION_DAYS)
        )).first()
        owns = (await db.execute(
            select(UserCard.id).where(UserCard.owner_id == user.id, UserCard.player_id == player_id).limit(1)
        )).first()
        if reached and not owns:
            due.append((CENTURION, Bundle(player_id=player_id, badge_id=s["centurion_badge_id"])))
    return due


async def check(db: AsyncSession, user: User) -> None:
    """Grants every keepsake now due. Once a day per player (core/dependencies).
    Commits."""
    config = await get_config(db)
    s = settings(config)
    if not s["enabled"]:
        return
    have = set((await db.execute(
        select(LoyaltyReward.code).where(LoyaltyReward.user_id == user.id)
    )).scalars().all())
    due = await _due(db, user, s, have)
    for code, bundle in due:
        locked = await lock_user_for_update(db, user.id)
        try:
            async with db.begin_nested():
                row = LoyaltyReward(user_id=locked.id, code=code, rewards={})
                db.add(row)
                await db.flush()
        except IntegrityError:
            continue  # a concurrent request granted it
        title, text = TITLES[code]
        granted = await reward_bundle_service.grant(
            db, locked, bundle, tx_type=TransactionType.achievement_reward,
            description=f"«{title}» в VICTOR FC", card_source=CardSource.task,
            idempotency_prefix=f"loyalty-{code}", cosmetic_source="loyalty",
        )
        row.rewards = granted.model_dump(mode="json")
        await notification_service.notify(db, locked.id, NotificationType.admin_message, f"🏅 {title}", text)
    if due:
        await db.commit()


async def unseen(db: AsyncSession, user: User) -> list[LoyaltyReward]:
    return list((await db.execute(
        select(LoyaltyReward).where(LoyaltyReward.user_id == user.id, LoyaltyReward.seen_at.is_(None))
        .order_by(LoyaltyReward.id)
    )).scalars().all())


async def mark_seen(db: AsyncSession, user: User, reward_id: int) -> None:
    row = await db.get(LoyaltyReward, reward_id)
    if row is None or row.user_id != user.id:
        raise NotFoundError("Награда не найдена")
    if row.seen_at is None:
        row.seen_at = _now()
        await db.commit()


# --- «Страховка серии» ---------------------------------------------------------------


async def note_streak_change(
    db: AsyncSession, user: User, old_streak: int, previous_day: Optional[date], today: date,
) -> None:
    """Called where the streak moves (core/dependencies), before it's
    committed: one missed day of a long streak keeps the old length for a
    while; a longer break forgets it."""
    if previous_day is None or previous_day >= today - timedelta(days=1):
        return  # first visit or the streak simply went on
    s = settings(await get_config(db))
    if (s["enabled"] and s["streak_save_enabled"] and previous_day == today - timedelta(days=2)
            and old_streak >= max(s["streak_save_min_streak"], 2)):
        user.streak_saved_value = old_streak
        user.streak_saved_until = _now() + timedelta(hours=s["streak_save_hours"])
    else:
        user.streak_saved_value = None
        user.streak_saved_until = None


def _can_save(user: User) -> bool:
    until = _aware(user.streak_saved_until)
    return bool(user.streak_saved_value) and until is not None and until > _now()


async def _free_available(db: AsyncSession, user: User, s: dict) -> bool:
    from app.services import club_pass_service

    used = _aware(user.streak_save_free_used_at)
    if used is not None and used > _now() - timedelta(days=s["streak_save_free_period_days"]):
        return False
    return await club_pass_service.is_subscriber(db, user.id)


def _restore(user: User) -> int:
    """The saved length goes back on top of the streak that started again."""
    user.daily_login_streak = (user.streak_saved_value or 0) + user.daily_login_streak
    user.streak_saved_value = None
    user.streak_saved_until = None
    return user.daily_login_streak


async def status(db: AsyncSession, user: User) -> dict:
    """«Путь к Центуриону» + the streak save offer, for the home card."""
    from app.schemas.player import PlayerOut
    from app.services.streak_reward_service import milestones

    config = await get_config(db)
    s = settings(config)
    steps = milestones(config)
    have = set((await db.execute(
        select(StreakReward.days).where(StreakReward.user_id == user.id)
    )).scalars().all())
    player = await db.get(Player, s["centurion_player_id"]) if s["centurion_player_id"] else None
    save = None
    if s["enabled"] and s["streak_save_enabled"] and _can_save(user):
        save = {
            "saved_streak": user.streak_saved_value,
            "until": _aware(user.streak_saved_until),
            "restored_streak": user.streak_saved_value + user.daily_login_streak,
            "price_stars": s["streak_save_stars"],
            "free_available": await _free_available(db, user, s),
        }
    return {
        "enabled": bool(s["enabled"]),
        "streak": user.daily_login_streak,
        "goal": CENTURION_DAYS,
        "milestones": [
            {"days": m["days"], "reached": m["days"] in have,
             "exclusive": bool(m.get("player_id")), "coins": m.get("coins") or 0,
             "card_rarity": m.get("card_rarity")}
            for m in steps if m["days"] <= CENTURION_DAYS
        ],
        "centurion": PlayerOut.model_validate(player) if player else None,
        "centurion_owned": CENTURION_DAYS in have,
        "streak_save": save,
    }


async def restore_free(db: AsyncSession, user: User) -> int:
    from app.services.streak_reward_service import check as check_streak

    s = settings(await get_config(db))
    locked = await lock_user_for_update(db, user.id)
    if not (s["enabled"] and s["streak_save_enabled"] and _can_save(locked)):
        raise ConflictError("Спасать нечего — серия не прерывалась или время вышло")
    if not await _free_available(db, locked, s):
        raise ConflictError("Бесплатная страховка — раз в месяц по клубному абонементу")
    locked.streak_save_free_used_at = _now()
    streak = _restore(locked)
    db.add(locked)
    await db.commit()
    await check_streak(db, locked)
    return streak


async def stars_order(db: AsyncSession, user: User) -> tuple[str, int, str, str]:
    """(product, stars, title, description) for shop_product_service.create_invoice."""
    s = settings(await get_config(db))
    if not (s["enabled"] and s["streak_save_enabled"] and _can_save(user)):
        raise ConflictError("Спасать нечего — серия не прерывалась или время вышло")
    return (
        f"streak_save:{user.streak_saved_value}", s["streak_save_stars"], "Страховка серии",
        f"Вернуть серию {user.streak_saved_value} дней подряд: она продолжится с того места, где прервалась.",
    )


async def validate_stars(db: AsyncSession, user_id: int, arg: str, stars_amount: int) -> tuple[bool, str]:
    """Pre-checkout: the same streak is still savable at the same price."""
    s = settings(await get_config(db))
    user = await db.get(User, user_id)
    if user is None:
        return False, "Игрок не найден"
    if not (s["enabled"] and s["streak_save_enabled"] and _can_save(user)) or str(user.streak_saved_value) != arg:
        return False, "Серию уже не спасти — открой покупку заново"
    if s["streak_save_stars"] != stars_amount:
        return False, "Цена изменилась — открой покупку заново"
    return True, ""


async def deliver_stars(db: AsyncSession, user: User) -> dict:
    """Already paid: restores the saved length even if the window closed
    meanwhile (once per invoice — the caller holds the invoice lock and
    commits). Milestones reached this way are granted on the next visit."""
    locked = await lock_user_for_update(db, user.id)
    if not locked.streak_saved_value:
        # Restored another way between pre-checkout and delivery.
        logger.warning("streak_save: user %s paid with nothing to restore", locked.id)
        return {"kind": "streak_save", "restored": False, "streak": locked.daily_login_streak}
    streak = _restore(locked)
    db.add(locked)
    return {"kind": "streak_save", "restored": True, "streak": streak}
