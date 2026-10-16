"""«Имущество» of «Мой игрок»: status items (cars, real estate, stocks,
anything else) the admin curates (admin_lifestyle router) and players buy
for coins (here) or Telegram Stars (my_player_service.create_stars_invoice →
stars_payment_service → `grant`). One copy of an item per player; items
with max_supply are limited editions numbered by sale order.

Every item adds prestige and may carry one admin-set effect (EFFECTS):
faster freshness recovery, an XP bonus (both summed over everything the
player owns, see `effects_of`) or a weekly coin income claimed here
(`claim_income`, whole weeks only, at most INCOME_MAX_WEEKS at a time).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.enums import TransactionType
from app.models.lifestyle import LifestyleItem, UserLifestyleItem
from app.models.user import User
from app.services import wallet_service

CATEGORIES = {"car": "Гараж", "estate": "Недвижимость", "stocks": "Инвестиции", "other": "Другое"}
# effect code -> label template ({v} = effect_value).
EFFECTS = {
    "none": "",
    "freshness_regen": "+{v} свежести в час",
    "xp_bonus_pct": "+{v}% опыта",
    "weekly_income": "+{v} монет в неделю",
}
INCOME_WEEK = timedelta(days=7)
# Unclaimed income stops piling up after this many weeks.
INCOME_MAX_WEEKS = 4


def effect_label(item: LifestyleItem) -> str:
    template = EFFECTS.get(item.effect or "none", "")
    return template.format(v=item.effect_value) if template and item.effect_value > 0 else ""


def _income_weeks(row: UserLifestyleItem, now: datetime) -> int:
    since = ensure_aware(row.income_claimed_at or row.acquired_at)
    return max(0, min(INCOME_MAX_WEEKS, int((now - since) / INCOME_WEEK)))


def _income_ready(row: UserLifestyleItem, now: datetime) -> int:
    item = row.item
    if item.effect != "weekly_income" or item.effect_value <= 0:
        return 0
    return _income_weeks(row, now) * item.effect_value


def item_out(item: LifestyleItem, owned: Optional[UserLifestyleItem] = None, now: Optional[datetime] = None) -> dict:
    sold_out = item.max_supply is not None and item.sold_count >= item.max_supply
    next_income_at = None
    if owned is not None and item.effect == "weekly_income" and item.effect_value > 0:
        since = ensure_aware(owned.income_claimed_at or owned.acquired_at)
        next_income_at = (since + INCOME_WEEK * (_income_weeks(owned, now or datetime.now(timezone.utc)) + 1)).isoformat()
    return {
        "id": item.id, "name": item.name, "description": item.description, "category": item.category,
        "emoji": item.emoji, "image_path": item.image_path,
        "coins_price": item.coins_price, "stars_price": item.stars_price, "prestige": item.prestige,
        "max_supply": item.max_supply, "sold_count": item.sold_count, "sold_out": sold_out,
        "owned": owned is not None, "serial_number": owned.serial_number if owned else None,
        "effect": item.effect or "none", "effect_value": item.effect_value, "effect_label": effect_label(item),
        "income_ready": _income_ready(owned, now or datetime.now(timezone.utc)) if owned else 0,
        "next_income_at": next_income_at,
    }


async def _owned(db: AsyncSession, user_id: int) -> dict[int, UserLifestyleItem]:
    rows = (await db.execute(select(UserLifestyleItem).where(UserLifestyleItem.user_id == user_id))).unique().scalars().all()
    return {r.item_id: r for r in rows}


async def prestige_of(db: AsyncSession, user_id: int) -> int:
    return int((await db.execute(
        select(func.coalesce(func.sum(LifestyleItem.prestige), 0))
        .join(UserLifestyleItem, UserLifestyleItem.item_id == LifestyleItem.id)
        .where(UserLifestyleItem.user_id == user_id)
    )).scalar_one())


async def effects_of(db: AsyncSession, user_id: int) -> dict[str, int]:
    """Sum of every effect over what the player owns: {effect: total}."""
    rows = (await db.execute(
        select(LifestyleItem.effect, func.sum(LifestyleItem.effect_value))
        .join(UserLifestyleItem, UserLifestyleItem.item_id == LifestyleItem.id)
        .where(UserLifestyleItem.user_id == user_id, LifestyleItem.effect != "none")
        .group_by(LifestyleItem.effect)
    )).all()
    return {effect: int(total or 0) for effect, total in rows}


async def income_ready(db: AsyncSession, user_id: int, now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    return sum(_income_ready(r, now) for r in (await _owned(db, user_id)).values())


async def catalog(db: AsyncSession, user: User) -> dict:
    """Shop (active items) + everything the player owns (even items the
    admin has since switched off)."""
    now = datetime.now(timezone.utc)
    owned = await _owned(db, user.id)
    items = (await db.execute(
        select(LifestyleItem).order_by(LifestyleItem.sort_order, LifestyleItem.id)
    )).scalars().all()
    totals: dict[str, int] = {}
    for i in items:
        if i.id in owned and i.effect != "none":
            totals[i.effect] = totals.get(i.effect, 0) + i.effect_value
    return {
        "categories": [{"code": code, "label": label} for code, label in CATEGORIES.items()],
        "items": [item_out(i, owned.get(i.id), now) for i in items if i.is_active or i.id in owned],
        "prestige": sum(i.prestige for i in items if i.id in owned),
        "balance": user.balance,
        "effects": [
            {"effect": code, "value": totals[code], "label": EFFECTS[code].format(v=totals[code])}
            for code in EFFECTS if totals.get(code)
        ],
        "income_ready": sum(_income_ready(r, now) for r in owned.values()),
    }


async def public_view(db: AsyncSession, user_id: int) -> dict:
    owned = await _owned(db, user_id)
    items = [r.item for r in sorted(owned.values(), key=lambda r: (-r.item.prestige, r.item_id))]
    return {"items": [item_out(i, owned[i.id]) for i in items], "prestige": sum(i.prestige for i in items)}


async def _lock_item(db: AsyncSession, item_id: int) -> LifestyleItem:
    item = (await db.execute(
        select(LifestyleItem).where(LifestyleItem.id == item_id).with_for_update()
    )).scalar_one_or_none()
    if item is None:
        raise NotFoundError("Предмет не найден")
    return item


async def check_buyable(db: AsyncSession, user_id: int, item: LifestyleItem) -> None:
    if not item.is_active:
        raise ConflictError("Этот предмет больше не продаётся")
    if item.max_supply is not None and item.sold_count >= item.max_supply:
        raise ConflictError("Тираж распродан")
    if (await db.execute(select(UserLifestyleItem.id).where(
        UserLifestyleItem.user_id == user_id, UserLifestyleItem.item_id == item.id,
    ))).first():
        raise ConflictError("Уже есть в твоём имуществе")


async def grant(db: AsyncSession, user_id: int, item: LifestyleItem, source: str) -> UserLifestyleItem:
    """Adds `item` (already row-locked by the caller) to the player's
    property and numbers it within the edition. The caller commits."""
    item.sold_count += 1
    row = UserLifestyleItem(user_id=user_id, item_id=item.id, source=source, serial_number=item.sold_count)
    db.add(row)
    await db.flush()
    return row


async def buy_with_coins(db: AsyncSession, user: User, item_id: int) -> dict:
    item = await _lock_item(db, item_id)
    if item.coins_price <= 0:
        raise ConflictError("Этот предмет продаётся только за звёзды")
    await check_buyable(db, user.id, item)
    locked = await wallet_service.lock_user_for_update(db, user.id)
    await wallet_service.debit_coins(
        db, locked, item.coins_price, TransactionType.lifestyle_purchase, f"Имущество: {item.name}",
        related_object_type="lifestyle_item", related_object_id=item.id,
    )
    await grant(db, user.id, item, "coins")
    await db.commit()
    return await catalog(db, locked)


async def claim_income(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    """Pays every whole week of weekly_income due on the player's items.
    The user row lock serializes claims, so a week is never paid twice."""
    now = now or datetime.now(timezone.utc)
    locked = await wallet_service.lock_user_for_update(db, user.id)
    rows = (await db.execute(
        select(UserLifestyleItem).where(UserLifestyleItem.user_id == user.id)
        .execution_options(populate_existing=True)
    )).unique().scalars().all()
    total = 0
    for row in rows:
        amount = _income_ready(row, now)
        if amount <= 0:
            continue
        since = ensure_aware(row.income_claimed_at or row.acquired_at)
        # Every whole week elapsed is settled (weeks beyond the cap are
        # forfeited); the started week keeps counting.
        row.income_claimed_at = since + INCOME_WEEK * int((now - since) / INCOME_WEEK)
        total += amount
    if total <= 0:
        raise ConflictError("Доход ещё не накопился — он приходит раз в неделю")
    await wallet_service.credit_coins(
        db, locked, total, TransactionType.lifestyle_income, "Имущество: доход", related_object_type="lifestyle_income",
    )
    await db.commit()
    view = await catalog(db, locked)
    view["claimed"] = total
    return view
