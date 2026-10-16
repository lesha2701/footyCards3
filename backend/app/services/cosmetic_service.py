"""Cosmetics without power: profile frames, profile backgrounds and card frame
skins. Bought for coins or Stars, or granted by the calendar, club pass,
season pass and starter offer. Nothing here is read by match or rating
code — equipping only changes how things look."""
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import TransactionType
from app.models.monetization import Cosmetic, UserCosmetic
from app.models.user import User
from app.schemas.monetization import (
    CosmeticCatalogItemOut,
    CosmeticCatalogOut,
    CosmeticIn,
    CosmeticOut,
    EquippedCosmeticsOut,
)
from app.services.wallet_service import debit_coins, lock_user_for_update

SLOT_BY_KIND = {
    "profile_frame": "equipped_frame_id",
    "profile_background": "equipped_background_id",
    "card_skin": "equipped_card_skin_id",
}


async def owned_ids(db: AsyncSession, user_id: int) -> set[int]:
    rows = await db.execute(select(UserCosmetic.cosmetic_id).where(UserCosmetic.user_id == user_id))
    return {r[0] for r in rows.all()}


async def grant(db: AsyncSession, user_id: int, cosmetic_id: int, source: str) -> Optional[Cosmetic]:
    """Idempotent: owning it already is a no-op. Equips it into an empty slot."""
    cosmetic = await db.get(Cosmetic, cosmetic_id)
    if cosmetic is None:
        return None
    owned = (await db.execute(
        select(UserCosmetic.id).where(UserCosmetic.user_id == user_id, UserCosmetic.cosmetic_id == cosmetic_id)
    )).first()
    if not owned:
        try:
            async with db.begin_nested():
                db.add(UserCosmetic(user_id=user_id, cosmetic_id=cosmetic_id, source=source))
                await db.flush()
        except IntegrityError:
            pass  # a concurrent grant won — same ownership either way
    user = await db.get(User, user_id)
    slot = SLOT_BY_KIND.get(cosmetic.kind)
    if user is not None and slot and getattr(user, slot) is None:
        setattr(user, slot, cosmetic.id)
        db.add(user)
    return cosmetic


async def revoke(db: AsyncSession, user: User, cosmetic_id: int, source: str) -> None:
    """Takes back an item granted from `source` (e.g. a lapsed club pass)."""
    await db.execute(delete(UserCosmetic).where(
        UserCosmetic.user_id == user.id, UserCosmetic.cosmetic_id == cosmetic_id, UserCosmetic.source == source,
    ))
    still_owned = cosmetic_id in await owned_ids(db, user.id)
    if not still_owned:
        for slot in SLOT_BY_KIND.values():
            if getattr(user, slot) == cosmetic_id:
                setattr(user, slot, None)
        db.add(user)


async def equipped(db: AsyncSession, user: User) -> EquippedCosmeticsOut:
    ids = [user.equipped_frame_id, user.equipped_background_id, user.equipped_card_skin_id]
    wanted = [i for i in ids if i]
    styles: dict[int, str] = {}
    if wanted:
        rows = await db.execute(select(Cosmetic.id, Cosmetic.style_key).where(Cosmetic.id.in_(wanted)))
        styles = {cid: key for cid, key in rows.all()}
    return EquippedCosmeticsOut(
        frame=styles.get(user.equipped_frame_id),
        background=styles.get(user.equipped_background_id),
        card_skin=styles.get(user.equipped_card_skin_id),
    )


async def catalog(db: AsyncSession, user: User) -> CosmeticCatalogOut:
    owned = await owned_ids(db, user.id)
    rows = (await db.execute(select(Cosmetic).order_by(Cosmetic.kind, Cosmetic.sort_order, Cosmetic.id))).scalars()
    equipped_ids = {user.equipped_frame_id, user.equipped_background_id, user.equipped_card_skin_id}
    items = [
        CosmeticCatalogItemOut(
            **CosmeticOut.model_validate(c).model_dump(), owned=c.id in owned, equipped=c.id in equipped_ids,
        )
        for c in rows
        # Exclusives and switched-off items only show up once owned.
        if c.id in owned or (c.is_active and not c.is_exclusive)
    ]
    return CosmeticCatalogOut(items=items, equipped=await equipped(db, user), balance=user.balance)


def _check_buyable(cosmetic: Optional[Cosmetic]) -> Cosmetic:
    if cosmetic is None:
        raise NotFoundError("Предмет не найден")
    if not cosmetic.is_active or cosmetic.is_exclusive:
        raise ConflictError("Этот предмет не продаётся")
    return cosmetic


async def buy_with_coins(db: AsyncSession, user: User, cosmetic_id: int) -> CosmeticCatalogOut:
    cosmetic = _check_buyable(await db.get(Cosmetic, cosmetic_id))
    if cosmetic.coins_price <= 0:
        raise ConflictError("Этот предмет продаётся только за звёзды")
    locked = await lock_user_for_update(db, user.id)
    if cosmetic.id in await owned_ids(db, locked.id):
        raise ConflictError("Уже куплено")
    await debit_coins(
        db, locked, cosmetic.coins_price, TransactionType.cosmetic_purchase, f"Стиль: {cosmetic.name}",
        related_object_type="cosmetic", related_object_id=cosmetic.id,
    )
    await grant(db, locked.id, cosmetic.id, "coins")
    await db.commit()
    await db.refresh(locked)
    return await catalog(db, locked)


async def equip(db: AsyncSession, user: User, kind: str, cosmetic_id: Optional[int]) -> CosmeticCatalogOut:
    slot = SLOT_BY_KIND[kind]
    if cosmetic_id is not None:
        cosmetic = await db.get(Cosmetic, cosmetic_id)
        if cosmetic is None or cosmetic.kind != kind:
            raise NotFoundError("Предмет не найден")
        if cosmetic_id not in await owned_ids(db, user.id):
            raise ConflictError("Сначала получи этот предмет")
    setattr(user, slot, cosmetic_id)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return await catalog(db, user)


# --- Stars ("cosmetic:<id>", see shop_product_service) ---------------------------------


async def stars_order(db: AsyncSession, user: User, cosmetic_id: int) -> tuple[str, int, str, str]:
    cosmetic = _check_buyable(await db.get(Cosmetic, cosmetic_id))
    if cosmetic.stars_price <= 0:
        raise ConflictError("Этот предмет продаётся только за монеты")
    if cosmetic.id in await owned_ids(db, user.id):
        raise ConflictError("Уже куплено")
    return (
        f"cosmetic:{cosmetic.id}", cosmetic.stars_price, cosmetic.name,
        cosmetic.description or f"Украшение профиля: {cosmetic.name}. Только внешний вид — на игру не влияет.",
    )


async def validate_stars(db: AsyncSession, user_id: int, cosmetic_id: int, stars_amount: int) -> tuple[bool, str]:
    cosmetic = await db.get(Cosmetic, cosmetic_id)
    if cosmetic is None or not cosmetic.is_active or cosmetic.is_exclusive or cosmetic.stars_price != stars_amount:
        return False, "Этот предмет больше не продаётся"
    if cosmetic_id in await owned_ids(db, user_id):
        return False, "Уже куплено"
    return True, ""


async def deliver_stars(db: AsyncSession, user: User, cosmetic_id: int) -> dict:
    cosmetic = await grant(db, user.id, cosmetic_id, "stars")
    return {"kind": "cosmetic", "name": cosmetic.name if cosmetic else "Косметика"}


# --- admin ----------------------------------------------------------------------------


async def admin_list(db: AsyncSession) -> list[CosmeticOut]:
    rows = (await db.execute(select(Cosmetic).order_by(Cosmetic.kind, Cosmetic.sort_order, Cosmetic.id))).scalars()
    return [CosmeticOut.model_validate(c) for c in rows]


async def admin_create(db: AsyncSession, data: CosmeticIn) -> CosmeticOut:
    cosmetic = Cosmetic(**data.model_dump())
    db.add(cosmetic)
    await db.commit()
    await db.refresh(cosmetic)
    return CosmeticOut.model_validate(cosmetic)


async def admin_update(db: AsyncSession, cosmetic_id: int, data: CosmeticIn) -> CosmeticOut:
    cosmetic = await db.get(Cosmetic, cosmetic_id)
    if cosmetic is None:
        raise NotFoundError("Предмет не найден")
    for key, value in data.model_dump().items():
        setattr(cosmetic, key, value)
    await db.commit()
    await db.refresh(cosmetic)
    return CosmeticOut.model_validate(cosmetic)
