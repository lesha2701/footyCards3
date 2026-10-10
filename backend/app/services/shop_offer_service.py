"""Shop "предложение дня": one coin pack a day at a discount, at most one
discounted purchase per player per local day. The discount, the pack and
the once-a-day rule are all decided here on the server — the client only
says "I'm buying today's offer", never the price.
"""
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError
from app.core.timeutil import app_timezone, local_today
from app.models.pack import Pack
from app.models.user import User
from app.schemas.pack import PackOut
from app.services.game_config_service import get_config


def _is_on_sale(pack: Pack, now: datetime) -> bool:
    return (
        pack.is_active and pack.stars_price is None and pack.price > 0
        and (pack.available_from is None or now >= pack.available_from)
        and (pack.available_until is None or now <= pack.available_until)
    )


def discounted_price(price: int, discount_pct: int) -> int:
    return max(1, round(price * (100 - discount_pct) / 100))


async def todays_offer_pack(db: AsyncSession, today: Optional[date] = None) -> Optional[Pack]:
    """The configured pack, or (pack_id unset) a coin pack picked by date so
    every player sees the same offer and it changes daily. None when off."""
    config = await get_config(db)
    if not config.shop_daily_offer_enabled:
        return None
    now = datetime.now(timezone.utc)
    packs = (await db.execute(
        select(Pack).options(joinedload(Pack.rarity_probabilities)).order_by(Pack.id)
    )).unique().scalars().all()
    candidates = [p for p in packs if _is_on_sale(p, now)]
    if config.shop_daily_offer_pack_id is not None:
        return next((p for p in candidates if p.id == config.shop_daily_offer_pack_id), None)
    if not candidates:
        return None
    day = today or local_today()
    return candidates[day.toordinal() % len(candidates)]


async def get_offer(db: AsyncSession, user: User) -> Optional[dict]:
    pack = await todays_offer_pack(db)
    if pack is None:
        return None
    config = await get_config(db)
    today = local_today()
    tomorrow = datetime.combine(today + timedelta(days=1), time.min, tzinfo=app_timezone())
    return {
        "pack": PackOut.model_validate(pack),
        "discount_pct": config.shop_daily_offer_discount_pct,
        "price": discounted_price(pack.price, config.shop_daily_offer_discount_pct),
        "claimed_today": user.daily_offer_claimed_on == today,
        "ends_at": tomorrow,
    }


async def claim_offer_price(db: AsyncSession, locked_user: User, pack: Pack) -> int:
    """Called by pack_service.open_pack under the user row lock: validates
    that `pack` is today's offer and not yet bought today, marks it bought
    and returns the discounted price to charge."""
    offer_pack = await todays_offer_pack(db)
    if offer_pack is None or offer_pack.id != pack.id:
        raise ConflictError("Это предложение уже недоступно")
    today = local_today()
    if locked_user.daily_offer_claimed_on == today:
        raise ConflictError("Предложение дня уже куплено — новое завтра")
    config = await get_config(db)
    locked_user.daily_offer_claimed_on = today
    return discounted_price(pack.price, config.shop_daily_offer_discount_pct)
