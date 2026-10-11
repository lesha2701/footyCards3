"""«Имущество» of «Мой игрок»: status items (cars, real estate, stocks,
anything else) the admin curates (admin_lifestyle router) and players buy
for coins (here) or Telegram Stars (my_player_service.create_stars_invoice →
stars_payment_service → `grant`). One copy of an item per player; items
with max_supply are limited editions numbered by sale order. Items only add
prestige — they have no gameplay effect.
"""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import TransactionType
from app.models.lifestyle import LifestyleItem, UserLifestyleItem
from app.models.user import User
from app.services import wallet_service

CATEGORIES = {"car": "Гараж", "estate": "Недвижимость", "stocks": "Инвестиции", "other": "Другое"}


def item_out(item: LifestyleItem, owned: Optional[UserLifestyleItem] = None) -> dict:
    sold_out = item.max_supply is not None and item.sold_count >= item.max_supply
    return {
        "id": item.id, "name": item.name, "description": item.description, "category": item.category,
        "emoji": item.emoji, "image_path": item.image_path,
        "coins_price": item.coins_price, "stars_price": item.stars_price, "prestige": item.prestige,
        "max_supply": item.max_supply, "sold_count": item.sold_count, "sold_out": sold_out,
        "owned": owned is not None, "serial_number": owned.serial_number if owned else None,
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


async def catalog(db: AsyncSession, user: User) -> dict:
    """Shop (active items) + everything the player owns (even items the
    admin has since switched off)."""
    owned = await _owned(db, user.id)
    items = (await db.execute(
        select(LifestyleItem).order_by(LifestyleItem.sort_order, LifestyleItem.id)
    )).scalars().all()
    return {
        "categories": [{"code": code, "label": label} for code, label in CATEGORIES.items()],
        "items": [item_out(i, owned.get(i.id)) for i in items if i.is_active or i.id in owned],
        "prestige": sum(i.prestige for i in items if i.id in owned),
        "balance": user.balance,
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
