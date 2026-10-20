"""«Экипировка»: things a player's card wears, bought for coins or Stars and
kept in the owner's «Инвентарь».

A card has one slot per kind (SLOTS): Бутсы, Форма, Гетры и щитки, Перчатки
(goalkeepers only), Аксессуар — and one «Артефакт» slot. Every thing has one
small effect (EFFECTS):
  * rating     — +N to the card's rating in every mode (like the diamond/star
                 bonuses, player_stats_service.card_rating_bonus);
  * shot_pp    — +N percentage points to the shot accuracy of this card in
                 the tournament engine (player tournaments, careers) and in
                 Card Arena (match_service._equipment_adjusted);
  * dribble_pp — +N pp to its 1-on-1 dribble there; in Card Arena it lowers
                 the ball carrier's failure chance in one-on-one and
                 flank-run moments;
  * chemistry  — +N chemistry points when the card stands on its position
                 (chemistry_service).
A thing may be limited to a club / country (`cond_club`/`cond_country`:
«родная форма») — on another player it is worn but gives nothing. Wearing
`set_size` things of one collection on one card adds the collection's
`set_bonus_rating`. All of it is summed per card and capped by GameConfig
(equipment_max_rating / _pp / _chemistry), then written to the card row
(UserCard.equipment_*), so every mode reads it like any other card bonus.
`equipment_enabled=False` closes the shop and equipping and zeroes every
worn effect (recompute_all).

A copy never leaves its owner: selling/burning the card frees it (FK SET
NULL, plus `_worn_rows` ignoring rows that point at a card the user no
longer owns), and a trade takes the things off before the card changes hands
(detach_from_cards). Every write locks the owner row first
(wallet_service.lock_user_for_update), which serializes one user's
purchases/equips; coin purchases are idempotent via
(user_id, purchase_key).
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.card import UserCard
from app.models.enums import Position, TransactionType
from app.models.equipment import EquipmentCollection, EquipmentItem, UserEquipment
from app.models.game_config import GameConfig
from app.models.user import User
from app.services.game_config_service import get_config
from app.services.wallet_service import debit_coins, lock_user_for_update

SLOTS: dict[str, str] = {
    "boots": "Бутсы",
    "kit": "Форма",
    "socks": "Гетры и щитки",
    "gloves": "Перчатки",
    "accessory": "Аксессуар",
    "artifact": "Артефакт",
}
EFFECTS: dict[str, str] = {
    "rating": "+{v} к рейтингу",
    "shot_pp": "+{v}% к точности удара",
    "dribble_pp": "+{v}% к обыгрышу 1 на 1",
    "chemistry": "+{v} к химии",
}
RARITIES = ("common", "rare", "epic", "legendary")
GK_ONLY_SLOTS = {"gloves"}


def effect_label(effect: str, value: int) -> str:
    return EFFECTS.get(effect, "").format(v=value)


def _key(value: Optional[str]) -> Optional[str]:
    return " ".join(value.split()).casefold() if isinstance(value, str) and value.strip() else None


def item_applies(item: EquipmentItem, player) -> bool:
    """Whether the thing's effect works on this player (club/country
    condition; gloves only on a goalkeeper)."""
    if item.slot in GK_ONLY_SLOTS and player.position != Position.GK:
        return False
    if item.cond_club and _key(item.cond_club) != _key(player.club):
        return False
    if item.cond_country and _key(item.cond_country) != _key(player.country):
        return False
    return True


def compute_effects(player, items: list[EquipmentItem], config: GameConfig) -> tuple[int, int, Optional[dict]]:
    """(rating, chemistry, boosts) of everything one card wears, capped."""
    if not config.equipment_enabled:
        return 0, 0, None
    totals = {"rating": 0, "shot_pp": 0, "dribble_pp": 0, "chemistry": 0}
    per_collection: dict[int, int] = {}
    collections: dict[int, EquipmentCollection] = {}
    for item in items:
        if not item_applies(item, player):
            continue
        if item.effect in totals:
            totals[item.effect] += max(0, item.effect_value)
        if item.collection_id is not None and item.collection is not None and item.collection.is_active:
            per_collection[item.collection_id] = per_collection.get(item.collection_id, 0) + 1
            collections[item.collection_id] = item.collection
    for collection_id, count in per_collection.items():
        collection = collections[collection_id]
        if count >= max(1, collection.set_size):
            totals["rating"] += max(0, collection.set_bonus_rating)
    rating = min(totals["rating"], max(0, config.equipment_max_rating))
    chemistry = min(totals["chemistry"], max(0, config.equipment_max_chemistry))
    boosts = {
        effect: min(totals[effect], max(0, config.equipment_max_pp))
        for effect in ("shot_pp", "dribble_pp") if totals[effect] > 0
    }
    return rating, chemistry, (boosts or None)


async def _worn_rows(db: AsyncSession, card: UserCard) -> list[UserEquipment]:
    result = await db.execute(
        select(UserEquipment).where(UserEquipment.user_card_id == card.id, UserEquipment.user_id == card.owner_id)
    )
    return list(result.unique().scalars().all())


async def recompute(db: AsyncSession, card: UserCard, config: Optional[GameConfig] = None) -> None:
    """Writes what the card wears onto its row (caller commits)."""
    config = config or await get_config(db)
    if card.player is None:
        await db.refresh(card, attribute_names=["player"])
    items = [row.item for row in await _worn_rows(db, card)]
    card.equipment_rating_bonus, card.equipment_chemistry, card.equipment_boosts = compute_effects(card.player, items, config)
    db.add(card)


async def recompute_all(db: AsyncSession) -> int:
    """After an admin change (switch, ceilings, a thing's effect): rewrites
    every card that wears something or still carries a bonus. Caller commits."""
    config = await get_config(db)
    worn_ids = set((await db.execute(
        select(UserEquipment.user_card_id).where(UserEquipment.user_card_id.is_not(None))
    )).scalars().all())
    carrying = set((await db.execute(
        select(UserCard.id).where(
            (UserCard.equipment_rating_bonus != 0) | (UserCard.equipment_chemistry != 0) | UserCard.equipment_boosts.is_not(None)
        )
    )).scalars().all())
    ids = sorted(worn_ids | carrying)
    if not ids:
        return 0
    cards = (await db.execute(
        select(UserCard).where(UserCard.id.in_(ids)).options(joinedload(UserCard.player))
    )).unique().scalars().all()
    for card in cards:
        await recompute(db, card, config)
    return len(cards)


async def detach_from_cards(db: AsyncSession, card_ids: list[int]) -> None:
    """A trade: the things come off before the cards change hands (they stay
    in their owner's inventory). Caller commits."""
    if not card_ids:
        return
    rows = (await db.execute(
        select(UserEquipment).where(UserEquipment.user_card_id.in_(card_ids)).execution_options(populate_existing=True)
    )).unique().scalars().all()
    for row in rows:
        row.user_card_id, row.slot = None, None
        db.add(row)
    # populate_existing: a card already in the session may hold a stale bonus.
    cards = (await db.execute(
        select(UserCard).where(UserCard.id.in_(card_ids)).execution_options(populate_existing=True)
    )).scalars().all()
    for card in cards:
        card.equipment_rating_bonus, card.equipment_chemistry, card.equipment_boosts = 0, 0, None
        db.add(card)
    await db.flush()


# --- read --------------------------------------------------------------------------------


def item_out(item: EquipmentItem) -> dict:
    return {
        "id": item.id, "name": item.name, "description": item.description, "image_path": item.image_path,
        "icon": item.icon, "slot": item.slot, "slot_label": SLOTS.get(item.slot, item.slot), "rarity": item.rarity,
        "collection_id": item.collection_id, "collection_name": item.collection.name if item.collection else None,
        "effect": item.effect, "effect_value": item.effect_value, "effect_label": effect_label(item.effect, item.effect_value),
        "cond_club": item.cond_club, "cond_country": item.cond_country,
        "coins_price": item.coins_price, "stars_price": item.stars_price,
    }


def collection_out(collection: EquipmentCollection) -> dict:
    return {
        "id": collection.id, "name": collection.name, "description": collection.description,
        "image_path": collection.image_path, "set_size": collection.set_size, "set_bonus_rating": collection.set_bonus_rating,
    }


async def _owned(db: AsyncSession, user_id: int) -> list[UserEquipment]:
    result = await db.execute(select(UserEquipment).where(UserEquipment.user_id == user_id).order_by(UserEquipment.id))
    rows = list(result.unique().scalars().all())
    worn_ids = {r.user_card_id for r in rows if r.user_card_id is not None}
    if worn_ids:
        mine = set((await db.execute(
            select(UserCard.id).where(UserCard.id.in_(worn_ids), UserCard.owner_id == user_id)
        )).scalars().all())
        for row in rows:
            # The card is gone or no longer ours: the copy is simply free.
            if row.user_card_id is not None and row.user_card_id not in mine:
                row.user_card_id, row.slot = None, None
    return rows


async def shop(db: AsyncSession, user: User) -> dict:
    config = await get_config(db)
    items = (await db.execute(
        select(EquipmentItem).where(EquipmentItem.is_active.is_(True))
        .order_by(EquipmentItem.sort_order, EquipmentItem.id)
    )).unique().scalars().all()
    collections = (await db.execute(
        select(EquipmentCollection).where(EquipmentCollection.is_active.is_(True))
        .order_by(EquipmentCollection.sort_order, EquipmentCollection.id)
    )).scalars().all()
    owned: dict[int, int] = {}
    for row in await _owned(db, user.id):
        owned[row.item_id] = owned.get(row.item_id, 0) + 1
    sellable = [i for i in items if i.coins_price > 0 or i.stars_price > 0]
    return {
        "enabled": bool(config.equipment_enabled),
        "slots": [{"code": code, "label": label} for code, label in SLOTS.items()],
        "caps": {"rating": config.equipment_max_rating, "pp": config.equipment_max_pp, "chemistry": config.equipment_max_chemistry},
        "collections": [
            {**collection_out(c), "items": [{**item_out(i), "owned": owned.get(i.id, 0)} for i in sellable if i.collection_id == c.id]}
            for c in collections
        ],
        "singles": [
            {**item_out(i), "owned": owned.get(i.id, 0)}
            for i in sellable if i.collection_id is None or i.collection_id not in {c.id for c in collections}
        ],
    }


async def inventory(db: AsyncSession, user: User) -> dict:
    rows = await _owned(db, user.id)
    card_ids = {r.user_card_id for r in rows if r.user_card_id is not None}
    names: dict[int, str] = {}
    if card_ids:
        cards = (await db.execute(
            select(UserCard).where(UserCard.id.in_(card_ids)).options(joinedload(UserCard.player))
        )).unique().scalars().all()
        names = {c.id: f"{c.player.display_name} #{c.serial_number}" for c in cards}
    return {
        "enabled": bool((await get_config(db)).equipment_enabled),
        "items": [
            {"copy_id": r.id, "item": item_out(r.item), "user_card_id": r.user_card_id, "card_name": names.get(r.user_card_id)}
            for r in rows
        ],
    }


async def card_equipment(db: AsyncSession, user: User, card_id: int) -> dict:
    config = await get_config(db)
    card = await _own_card(db, user.id, card_id)
    rows = await _owned(db, user.id)
    worn = {r.slot: r for r in rows if r.user_card_id == card.id}
    free = [r for r in rows if r.user_card_id is None]
    return {
        "enabled": bool(config.equipment_enabled),
        "card_id": card.id,
        "rating_bonus": card.equipment_rating_bonus,
        "chemistry": card.equipment_chemistry,
        "boosts": card.equipment_boosts or {},
        "slots": [
            {
                "code": code, "label": label,
                "available": not (code in GK_ONLY_SLOTS and card.player.position != Position.GK),
                "worn": (
                    {"copy_id": worn[code].id, "item": item_out(worn[code].item),
                     "applies": item_applies(worn[code].item, card.player)}
                    if code in worn else None
                ),
                # Free copies of things for this slot (one per kind is enough to pick).
                "options": [
                    {"copy_id": r.id, "item": item_out(r.item), "applies": item_applies(r.item, card.player)}
                    for r in {r.item_id: r for r in free if r.item.slot == code}.values()
                ],
            }
            for code, label in SLOTS.items()
        ],
    }


# --- write -------------------------------------------------------------------------------


def _check_enabled(config: GameConfig) -> None:
    if not config.equipment_enabled:
        raise ConflictError("Экипировка сейчас недоступна", details={"reason": "disabled"})


async def _own_card(db: AsyncSession, user_id: int, card_id: int, lock: bool = False) -> UserCard:
    query = select(UserCard).where(UserCard.id == card_id).options(joinedload(UserCard.player))
    if lock:
        query = query.with_for_update(of=UserCard).execution_options(populate_existing=True)
    card = (await db.execute(query)).unique().scalar_one_or_none()
    if card is None or card.owner_id != user_id:
        raise NotFoundError("Card not found")
    return card


async def _own_copy(db: AsyncSession, user_id: int, copy_id: int) -> UserEquipment:
    row = (await db.execute(
        select(UserEquipment).where(UserEquipment.id == copy_id)
        .with_for_update(of=UserEquipment).execution_options(populate_existing=True)
    )).unique().scalar_one_or_none()
    if row is None or row.user_id != user_id:
        raise NotFoundError("Вещь не найдена")
    return row


def _check_buyable(item: Optional[EquipmentItem]) -> EquipmentItem:
    if item is None:
        raise NotFoundError("Вещь не найдена")
    if not item.is_active:
        raise ConflictError("Эта вещь не продаётся")
    return item


async def buy_with_coins(db: AsyncSession, user: User, item_id: int, purchase_key: Optional[str] = None) -> dict:
    config = await get_config(db)
    _check_enabled(config)
    if purchase_key:
        existing = (await db.execute(
            select(UserEquipment).where(UserEquipment.user_id == user.id, UserEquipment.purchase_key == purchase_key)
        )).unique().scalar_one_or_none()
        if existing is not None:
            await db.refresh(user)
            return {"copy_id": existing.id, "new_balance": user.balance, "replayed": True}
    locked = await lock_user_for_update(db, user.id)
    item = _check_buyable(await db.get(EquipmentItem, item_id))
    if item.coins_price <= 0:
        raise ConflictError("Эта вещь продаётся только за звёзды")
    await debit_coins(
        db, locked, item.coins_price, TransactionType.equipment_purchase, f"Экипировка «{item.name}»",
        related_object_type="equipment_item", related_object_id=item.id,
    )
    row = UserEquipment(user_id=locked.id, item_id=item.id, source="coins", purchase_key=purchase_key)
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return await buy_with_coins(db, user, item_id, purchase_key)
    await db.refresh(locked)
    return {"copy_id": row.id, "new_balance": locked.balance, "replayed": False}


async def equip(db: AsyncSession, user: User, copy_id: int, card_id: int) -> dict:
    config = await get_config(db)
    _check_enabled(config)
    locked = await lock_user_for_update(db, user.id)
    row = await _own_copy(db, locked.id, copy_id)
    card = await _own_card(db, locked.id, card_id, lock=True)
    if card.is_locked_by_admin or card.is_locked_in_trade:
        raise ConflictError("Карточка в обмене или заблокирована — экипировку менять нельзя")
    slot = row.item.slot
    if slot not in SLOTS:
        raise ConflictError("Неизвестный слот вещи")
    if slot in GK_ONLY_SLOTS and card.player.position != Position.GK:
        raise ConflictError("Перчатки можно надеть только вратарю")

    touched: dict[int, UserCard] = {card.id: card}
    if row.user_card_id is not None and row.user_card_id != card.id:
        previous = (await db.execute(
            select(UserCard).where(UserCard.id == row.user_card_id).options(joinedload(UserCard.player))
        )).unique().scalar_one_or_none()
        if previous is not None and previous.owner_id == locked.id:
            touched[previous.id] = previous
    occupant = (await db.execute(
        select(UserEquipment).where(UserEquipment.user_card_id == card.id, UserEquipment.slot == slot, UserEquipment.id != row.id)
        .with_for_update(of=UserEquipment)
    )).unique().scalar_one_or_none()
    if occupant is not None:
        occupant.user_card_id, occupant.slot = None, None
        db.add(occupant)
    row.user_card_id, row.slot = None, None
    await db.flush()
    row.user_card_id, row.slot = card.id, slot
    db.add(row)
    await db.flush()
    for touched_card in touched.values():
        await recompute(db, touched_card, config)
    await db.commit()
    return await card_equipment(db, locked, card.id)


async def unequip(db: AsyncSession, user: User, copy_id: int) -> dict:
    config = await get_config(db)
    locked = await lock_user_for_update(db, user.id)
    row = await _own_copy(db, locked.id, copy_id)
    if row.user_card_id is None:
        return await inventory(db, locked)
    card = (await db.execute(
        select(UserCard).where(UserCard.id == row.user_card_id).options(joinedload(UserCard.player))
        .with_for_update(of=UserCard).execution_options(populate_existing=True)
    )).unique().scalar_one_or_none()
    if card is not None and card.is_locked_in_trade:
        raise ConflictError("Карточка в обмене — экипировку менять нельзя")
    row.user_card_id, row.slot = None, None
    db.add(row)
    await db.flush()
    if card is not None and card.owner_id == locked.id:
        await recompute(db, card, config)
    await db.commit()
    return await inventory(db, locked)


# --- Stars ("equipment:<id>", see shop_product_service) ----------------------------------


async def stars_order(db: AsyncSession, user: User, item_id: int) -> tuple[str, int, str, str]:
    _check_enabled(await get_config(db))
    item = _check_buyable(await db.get(EquipmentItem, item_id))
    if item.stars_price <= 0:
        raise ConflictError("Эта вещь продаётся только за монеты")
    effect = effect_label(item.effect, item.effect_value)
    return (
        f"equipment:{item.id}", item.stars_price, item.name,
        f"Экипировка ({SLOTS.get(item.slot, item.slot).lower()}){': ' + effect if effect else ''}. " + (item.description or ""),
    )


async def validate_stars(db: AsyncSession, user_id: int, item_id: int, stars_amount: int) -> tuple[bool, str]:
    if not (await get_config(db)).equipment_enabled:
        return False, "Экипировка сейчас недоступна"
    item = await db.get(EquipmentItem, item_id)
    if item is None or not item.is_active or item.stars_price != stars_amount:
        return False, "Эта вещь больше не продаётся"
    return True, ""


async def deliver_stars(db: AsyncSession, user: User, item_id: int) -> dict:
    """Already paid: the copy is delivered even if the thing was switched
    off meanwhile. The caller commits."""
    item = await db.get(EquipmentItem, item_id)
    db.add(UserEquipment(user_id=user.id, item_id=item_id, source="stars"))
    await db.flush()
    return {"kind": "equipment", "name": item.name if item else "Экипировка"}


# --- admin -------------------------------------------------------------------------------


def admin_item_out(item: EquipmentItem) -> dict:
    return {**item_out(item), "is_active": item.is_active, "sort_order": item.sort_order}


def admin_collection_out(collection: EquipmentCollection) -> dict:
    return {**collection_out(collection), "is_active": collection.is_active, "sort_order": collection.sort_order}


async def admin_catalog(db: AsyncSession) -> dict:
    items = (await db.execute(select(EquipmentItem).order_by(EquipmentItem.sort_order, EquipmentItem.id))).unique().scalars().all()
    collections = (await db.execute(
        select(EquipmentCollection).order_by(EquipmentCollection.sort_order, EquipmentCollection.id)
    )).scalars().all()
    return {
        "slots": [{"code": code, "label": label} for code, label in SLOTS.items()],
        "effects": [{"code": code, "label": label.format(v="N")} for code, label in EFFECTS.items()],
        "rarities": list(RARITIES),
        "collections": [admin_collection_out(c) for c in collections],
        "items": [admin_item_out(i) for i in items],
    }


def _validate_item(data: dict) -> None:
    if data.get("slot") is not None and data["slot"] not in SLOTS:
        raise ConflictError(f"Неизвестный слот: {data['slot']}")
    if data.get("effect") is not None and data["effect"] not in EFFECTS:
        raise ConflictError(f"Неизвестный эффект: {data['effect']}")
    if data.get("rarity") is not None and data["rarity"] not in RARITIES:
        raise ConflictError(f"Неизвестная редкость: {data['rarity']}")


async def admin_save_item(db: AsyncSession, data: dict, item_id: Optional[int] = None) -> dict:
    _validate_item(data)
    if data.get("collection_id") and await db.get(EquipmentCollection, data["collection_id"]) is None:
        raise NotFoundError("Коллекция не найдена")
    if item_id is None:
        item = EquipmentItem(**data)
        db.add(item)
    else:
        item = await db.get(EquipmentItem, item_id)
        if item is None:
            raise NotFoundError("Вещь не найдена")
        for key, value in data.items():
            setattr(item, key, value)
    await db.flush()
    # Effect, condition, slot or set membership may have changed for cards wearing it.
    await recompute_all(db)
    await db.commit()
    await db.refresh(item)
    return admin_item_out(item)


async def admin_save_collection(db: AsyncSession, data: dict, collection_id: Optional[int] = None) -> dict:
    if collection_id is None:
        collection = EquipmentCollection(**data)
        db.add(collection)
    else:
        collection = await db.get(EquipmentCollection, collection_id)
        if collection is None:
            raise NotFoundError("Коллекция не найдена")
        for key, value in data.items():
            setattr(collection, key, value)
    await db.flush()
    await recompute_all(db)
    await db.commit()
    await db.refresh(collection)
    return admin_collection_out(collection)


async def admin_grant(db: AsyncSession, item_id: int, user_id: int) -> dict:
    if await db.get(EquipmentItem, item_id) is None:
        raise NotFoundError("Вещь не найдена")
    if await db.get(User, user_id) is None:
        raise NotFoundError("Пользователь не найден")
    row = UserEquipment(user_id=user_id, item_id=item_id, source="admin")
    db.add(row)
    await db.commit()
    return {"copy_id": row.id}
