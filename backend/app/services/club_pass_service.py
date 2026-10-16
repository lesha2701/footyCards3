"""«Клубный абонемент»: a monthly Telegram Stars subscription
(createInvoiceLink with subscription_period = 30 days). Telegram charges the
renewals itself and sends each as a new successful_payment with the original
payload (see stars_payment_service._deliver_subscription_renewal); the
player — or we, via editUserStarSubscription — can switch auto-renewal off,
and the perks simply stop at `expires_at`.

Perks while active (all GameConfig.club_pass_*): a daily bonus (coins + a
pack), +N rewarded attempts in every mini-game, an exclusive profile frame
and badge (granted on payment, taken back once the pass lapses) and an
"ad-free" flag for the future."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.badge import Badge, UserBadge
from app.models.enums import CardSource, TransactionType
from app.models.game_config import GameConfig
from app.models.monetization import ClubSubscription, Cosmetic
from app.models.user import User
from app.schemas.badge import BadgeOut
from app.schemas.monetization import ClubPassOut, ClubPassPerksOut, CosmeticOut, GrantedRewardsOut
from app.services import cosmetic_service, reward_bundle_service
from app.services.game_config_service import get_config
from app.services.reward_bundle_service import Bundle
from app.services.wallet_service import lock_user_for_update

settings = get_settings()
logger = logging.getLogger(__name__)

PERIOD = timedelta(days=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_active(sub: Optional[ClubSubscription], now: Optional[datetime] = None) -> bool:
    return sub is not None and ensure_aware(sub.expires_at) > (now or _now())


async def get_subscription(db: AsyncSession, user_id: int, lock: bool = False) -> Optional[ClubSubscription]:
    query = select(ClubSubscription).where(ClubSubscription.user_id == user_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(query)).scalar_one_or_none()


async def extra_rewarded_attempts(db: AsyncSession, user_id: int, config: GameConfig) -> int:
    """Added to every mini-game's daily rewarded-attempt cap while active."""
    if not config.club_pass_extra_rewarded_attempts:
        return 0
    return config.club_pass_extra_rewarded_attempts if is_active(await get_subscription(db, user_id)) else 0


async def _grant_perk_items(db: AsyncSession, user: User, config: GameConfig) -> None:
    if config.club_pass_frame_cosmetic_id:
        await cosmetic_service.grant(db, user.id, config.club_pass_frame_cosmetic_id, "club_pass")
    if config.club_pass_badge_id:
        await reward_bundle_service.grant_badge(db, user, config.club_pass_badge_id)


async def _revoke_perk_items(db: AsyncSession, user: User, config: GameConfig) -> None:
    if config.club_pass_frame_cosmetic_id:
        await cosmetic_service.revoke(db, user, config.club_pass_frame_cosmetic_id, "club_pass")
    if config.club_pass_badge_id:
        await db.execute(delete(UserBadge).where(
            UserBadge.user_id == user.id, UserBadge.badge_id == config.club_pass_badge_id,
        ))
        if user.active_badge_id == config.club_pass_badge_id:
            user.active_badge_id = None
            db.add(user)


async def expire_if_needed(db: AsyncSession, user: User) -> None:
    """Lazy sweep (no scheduler): once a pass has lapsed, take back its
    exclusive frame and badge. Called whenever the player's profile, pass or
    cosmetics are read."""
    sub = await get_subscription(db, user.id)
    if sub is None or not sub.perks_granted or is_active(sub):
        return
    sub = await get_subscription(db, user.id, lock=True)
    if sub is None or not sub.perks_granted or is_active(sub):
        return
    await _revoke_perk_items(db, user, await get_config(db))
    sub.perks_granted = False
    await db.commit()
    await db.refresh(user)


async def _perks(db: AsyncSession, config: GameConfig) -> ClubPassPerksOut:
    frame = await db.get(Cosmetic, config.club_pass_frame_cosmetic_id) if config.club_pass_frame_cosmetic_id else None
    badge = await db.get(Badge, config.club_pass_badge_id) if config.club_pass_badge_id else None
    return ClubPassPerksOut(
        daily_coins=config.club_pass_daily_coins,
        daily_pack=await reward_bundle_service.describe(db, Bundle(pack_id=config.club_pass_daily_pack_id))
        if config.club_pass_daily_pack_id else None,
        extra_rewarded_attempts=config.club_pass_extra_rewarded_attempts,
        frame=CosmeticOut.model_validate(frame) if frame else None,
        badge=BadgeOut.model_validate(badge) if badge else None,
        ad_free=config.club_pass_ad_free,
    )


async def get_status(db: AsyncSession, user: User) -> ClubPassOut:
    await expire_if_needed(db, user)
    config = await get_config(db)
    sub = await get_subscription(db, user.id)
    active = is_active(sub)
    return ClubPassOut(
        enabled=config.club_pass_enabled, stars_price=config.club_pass_stars, perks=await _perks(db, config),
        is_active=active, expires_at=sub.expires_at if sub else None,
        auto_renew=bool(active and sub.auto_renew),
        daily_claimed_today=bool(active and sub.last_daily_claim == local_today()),
    )


def _perk_lines(perks: ClubPassPerksOut) -> str:
    lines = []
    if perks.daily_coins:
        lines.append(f"+{perks.daily_coins} монет каждый день")
    if perks.daily_pack and perks.daily_pack.pack_name:
        lines.append(f"пак «{perks.daily_pack.pack_name}» каждый день")
    if perks.extra_rewarded_attempts:
        lines.append(f"+{perks.extra_rewarded_attempts} награждаемая попытка в мини-играх")
    if perks.frame:
        lines.append(f"рамка «{perks.frame.name}»")
    if perks.badge:
        lines.append(f"значок «{perks.badge.name}»")
    return ", ".join(lines)


async def stars_order(db: AsyncSession, user: User) -> tuple[str, int, str, str]:
    config = await get_config(db)
    if not config.club_pass_enabled:
        raise ConflictError("Абонемент сейчас недоступен")
    sub = await get_subscription(db, user.id)
    if is_active(sub):
        raise ConflictError(
            "Абонемент уже активен" if sub.auto_renew else "Абонемент активен — включи автопродление вместо новой покупки"
        )
    perks = await _perks(db, config)
    return (
        "club_pass", config.club_pass_stars, "Клубный абонемент",
        f"30 дней, продлевается автоматически (отменить можно в любой момент): {_perk_lines(perks)}.",
    )


async def validate_stars(db: AsyncSession, user_id: int, stars_amount: int) -> tuple[bool, str]:
    config = await get_config(db)
    if not config.club_pass_enabled:
        return False, "Абонемент сейчас недоступен"
    if config.club_pass_stars != stars_amount:
        return False, "Цена абонемента изменилась — открой покупку заново"
    if is_active(await get_subscription(db, user_id)):
        return False, "Абонемент уже активен"
    return True, ""


async def deliver_payment(
    db: AsyncSession, user: User, charge_id: str, subscription_expiration: Optional[int], is_renewal: bool,
) -> dict:
    """First payment or a renewal (already paid — never refuses). The new
    end is Telegram's subscription_expiration_date when the bot passed it,
    otherwise 30 days on top of the current period (or of now). The caller
    commits."""
    locked = await lock_user_for_update(db, user.id)
    config = await get_config(db)
    now = _now()
    sub = await get_subscription(db, locked.id, lock=True)
    if sub is None:
        sub = ClubSubscription(user_id=locked.id, expires_at=now, auto_renew=True, payments=0)
        db.add(sub)
    base = max(ensure_aware(sub.expires_at), now)
    new_end = base + PERIOD
    if subscription_expiration:
        new_end = max(datetime.fromtimestamp(subscription_expiration, tz=timezone.utc), base)
    sub.expires_at = new_end
    sub.payments += 1
    if not is_renewal:
        sub.telegram_charge_id = charge_id
        sub.auto_renew = True
    await _grant_perk_items(db, locked, config)
    sub.perks_granted = True
    await db.flush()
    return {"kind": "club_pass", "expires_at": new_end.isoformat(), "renewal": is_renewal}


async def claim_daily(db: AsyncSession, user: User) -> GrantedRewardsOut:
    config = await get_config(db)
    locked = await lock_user_for_update(db, user.id)
    sub = await get_subscription(db, locked.id, lock=True)
    if not is_active(sub):
        raise ConflictError("Абонемент не активен")
    today = local_today()
    if sub.last_daily_claim == today:
        raise ConflictError("Бонус абонемента на сегодня уже получен")
    sub.last_daily_claim = today
    granted = await reward_bundle_service.grant(
        db, locked, Bundle(coins=config.club_pass_daily_coins, pack_id=config.club_pass_daily_pack_id),
        tx_type=TransactionType.club_pass_reward, description="Клубный абонемент: ежедневный бонус",
        card_source=CardSource.stars_purchase, idempotency_prefix=f"club-pass-{locked.id}-{today.isoformat()}",
        cosmetic_source="club_pass", related_object_type="club_subscription", related_object_id=sub.id,
    )
    await db.commit()
    await db.refresh(locked)
    granted.new_balance = locked.balance
    return granted


async def _request_edit_subscription(telegram_user_id: int, charge_id: str, is_canceled: bool) -> None:
    """Bot API editUserStarSubscription. Split out so tests can monkeypatch
    the one Telegram call."""
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/editUserStarSubscription"
    try:
        async with httpx.AsyncClient(timeout=10, proxy=settings.telegram_proxy_url or None) as client:
            resp = await client.post(url, json={
                "user_id": telegram_user_id, "telegram_payment_charge_id": charge_id, "is_canceled": is_canceled,
            })
        data = resp.json()
    except httpx.HTTPError:
        logger.warning("editUserStarSubscription: request to Telegram failed", exc_info=True)
        raise ConflictError("Не удалось связаться с Telegram — попробуй ещё раз") from None
    if not data.get("ok"):
        raise ConflictError(f"Telegram не изменил подписку: {data.get('description', 'неизвестная ошибка')}")


async def set_auto_renew(db: AsyncSession, user: User, auto_renew: bool) -> ClubPassOut:
    sub = await get_subscription(db, user.id, lock=True)
    if not is_active(sub) or not sub.telegram_charge_id:
        raise NotFoundError("Активного абонемента нет")
    if sub.auto_renew != auto_renew:
        await _request_edit_subscription(user.telegram_id, sub.telegram_charge_id, is_canceled=not auto_renew)
        sub.auto_renew = auto_renew
        await db.commit()
    return await get_status(db, user)
