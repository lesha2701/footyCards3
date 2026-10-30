"""What a card is worth, which cards are «ценные», and who may give them.

Value (coins, GameConfig.card_values) is the floor of what a copy is worth —
roughly what getting it from us costs. It drives the trade equal-value rule
and is meant for market minimum prices:

- «Академия» (path) cards: academy[path_stage];
- diamonds: diamond;
- limited (not in packs, at most limited_max_copies minted): limited_* by
  rarity, limited_legendary_scarce at most limited_scarce_copies;
- legendaries: legendary, legendary_top from legendary_top_rating;
- anything else: quick_sell_price x sell_multiplier.

Valuable = legendary, diamond, «Академия» or limited. A valuable card may
leave an account (trade, later the market) only if it didn't come from a free
source (UserCard.from_free_source) and its owner is a «проверенный аккаунт»:
old enough (activity optional) and has spent at least
trade_verified_min_stars in our shop. Multi-accounts farming free rewards can then pass on nothing of value.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import ensure_aware
from app.models.enums import CardSource, Rarity
from app.models.game_config import GameConfig
from app.models.pack import PackOpening, StarsInvoice
from app.models.user import User
from app.models.user_activity import UserDailyActivity

DEFAULT_VALUES = {
    "legendary": 6000, "legendary_top": 12000, "legendary_top_rating": 93,
    "limited_legendary": 30000, "limited_legendary_scarce": 60000, "limited_epic": 10000,
    "limited_rare": 5000, "limited_max_copies": 50, "limited_scarce_copies": 15,
    "diamond": 60000, "academy": [40000, 40000, 60000, 60000, 100000], "sell_multiplier": 2,
}

# Free sources: a valuable copy from these never leaves the account. A pack
# opening counts as paid only if coins were paid for it (source "pack") or it
# was bought with Stars ("stars_purchase").
BOUND_SOURCES = frozenset({
    CardSource.daily_reward, CardSource.admin_grant, CardSource.achievement, CardSource.game_reward,
    CardSource.task, CardSource.free_pack, CardSource.newbie, CardSource.card_upgrade,
    CardSource.collection_reward, CardSource.chat_pack, CardSource.gift, CardSource.wheel,
    CardSource.league_reward, CardSource.club_reward,
})


def _values(config: Optional[GameConfig]) -> dict:
    return {**DEFAULT_VALUES, **((config.card_values if config is not None else None) or {})}


def _minted(player) -> int:
    return max(0, (getattr(player, "next_serial_number", 1) or 1) - 1)


def is_limited(player, config: Optional[GameConfig]) -> bool:
    values = _values(config)
    return (
        not getattr(player, "is_pack_droppable", True)
        and getattr(player, "path_talent_code", None) is None
        and player.rarity != Rarity.diamond
        and _minted(player) <= int(values["limited_max_copies"])
    )


def is_valuable(card, config: Optional[GameConfig]) -> bool:
    player = card.player
    return (
        player.rarity in (Rarity.legendary, Rarity.diamond)
        or getattr(player, "path_talent_code", None) is not None
        or is_limited(player, config)
    )


def card_value(card, config: Optional[GameConfig]) -> int:
    values = _values(config)
    player = card.player
    if getattr(player, "path_talent_code", None) is not None:
        academy = list(values["academy"]) or [0]
        stage = max(0, min(len(academy) - 1, int(getattr(card, "path_stage", 0) or 0)))
        return int(academy[stage])
    if player.rarity == Rarity.diamond:
        return int(values["diamond"])
    if is_limited(player, config):
        if player.rarity == Rarity.legendary:
            scarce = _minted(player) <= int(values["limited_scarce_copies"])
            return int(values["limited_legendary_scarce" if scarce else "limited_legendary"])
        if player.rarity == Rarity.epic:
            return int(values["limited_epic"])
        if player.rarity == Rarity.rare:
            return int(values["limited_rare"])
    if player.rarity == Rarity.legendary:
        top = player.rating >= int(values["legendary_top_rating"])
        return int(values["legendary_top" if top else "legendary"])
    return int((player.quick_sell_price or 0) * float(values["sell_multiplier"]))


def side_value(cards, coins: int, config: Optional[GameConfig]) -> int:
    return sum(card_value(c, config) for c in cards) + max(0, coins)


async def bound_at_creation(db: AsyncSession, source: CardSource, source_ref_id: Optional[int]) -> bool:
    """Whether a new copy is bound (free source). Pack cards carry their
    opening id: bound unless coins were paid for it."""
    if source in BOUND_SOURCES:
        return True
    if source == CardSource.pack:
        if source_ref_id is None:
            return True
        paid = (await db.execute(select(PackOpening.price_paid).where(PackOpening.id == source_ref_id))).scalar_one_or_none()
        return not paid
    return False


async def verified_block_reason(db: AsyncSession, user: User, config: GameConfig) -> Optional[str]:
    """Why `user` isn't a «проверенный аккаунт» yet (None = they are)."""
    missing = []
    days = config.trade_verified_min_age_days
    if days > 0 and user.created_at is not None:
        if datetime.now(timezone.utc) - ensure_aware(user.created_at) < timedelta(days=days):
            missing.append(f"аккаунту не меньше {days} дн.")
    active = config.trade_verified_min_active_days
    if active > 0:
        have = int((await db.execute(
            select(func.count()).select_from(UserDailyActivity).where(UserDailyActivity.user_id == user.id)
        )).scalar_one())
        if have < active:
            missing.append(f"не меньше {active} дн. в игре (сейчас {have})")
    stars = config.trade_verified_min_stars
    if stars > 0:
        spent = int((await db.execute(
            select(func.coalesce(func.sum(StarsInvoice.stars_amount), 0)).where(
                StarsInvoice.user_id == user.id, StarsInvoice.completed_at.is_not(None),
            )
        )).scalar_one())
        if spent < stars:
            missing.append(f"покупки в магазине за ⭐ на {stars}⭐ всего (сейчас {spent}⭐)")
    if not missing:
        return None
    return "Нужен «Проверенный аккаунт»: " + "; ".join(missing) + "."
