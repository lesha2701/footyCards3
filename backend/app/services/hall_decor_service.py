"""«Обустроить зал»: the look of the «Зал славы» — cosmetics only, never read
by game code. The room keeps fixed places; the owner picks what stands in
each one from cosmetics of the place's kind (bought in the usual cosmetics
shop for coins or Stars, prices on the `cosmetics` rows):

* skins: the cabinet and the pedestals (one look for all six);
* decor places: the floor corner by the right wall, the right wall itself,
  and the two places at the front of the room.

`users.hall_layout` maps a place to a cosmetic id, or to 0 for «пусто»; a
place that isn't there shows the default (the wood cabinet, marble
pedestals, the palm, the club pennant, velvet ropes)."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.monetization import Cosmetic
from app.models.user import User
from app.services import cosmetic_service

# place → cosmetics kind; the order is the order of the owner's tabs.
SLOTS: dict[str, str] = {
    "cabinet": "hall_cabinet",
    "pedestal": "hall_pedestal",
    "corner": "hall_floor",
    "wall": "hall_wall",
    "front_left": "hall_front",
    "front_right": "hall_front",
}
# Skins can't be emptied — the cabinet and pedestals hold the exhibits.
SKIN_SLOTS = ("cabinet", "pedestal")


async def view(db: AsyncSession, user: User) -> dict[str, Optional[dict]]:
    """Every place the owner changed: {id, style_key, image_path}, or None
    for an emptied one. A cosmetic no longer owned falls back to the default."""
    layout = {k: v for k, v in (user.hall_layout or {}).items() if k in SLOTS}
    if not layout:
        return {}
    ids = {v for v in layout.values() if v}
    owned = await cosmetic_service.owned_ids(db, user.id) if ids else set()
    rows = {}
    if ids:
        rows = {c.id: c for c in (await db.execute(select(Cosmetic).where(Cosmetic.id.in_(ids)))).scalars()}
    out: dict[str, Optional[dict]] = {}
    for slot, cid in layout.items():
        if not cid:
            if slot not in SKIN_SLOTS:
                out[slot] = None
            continue
        c = rows.get(cid)
        if c is not None and cid in owned and c.kind == SLOTS[slot]:
            out[slot] = {"id": c.id, "style_key": c.style_key, "image_path": c.image_path}
    return out


async def set_slot(db: AsyncSession, user: User, slot: str, cosmetic_id: Optional[int]) -> dict[str, Optional[dict]]:
    """`cosmetic_id`: an owned cosmetic of the place's kind, None = the
    default, 0 = empty (decor places only)."""
    kind = SLOTS.get(slot)
    if kind is None:
        raise NotFoundError("Такого места в зале нет")
    if cosmetic_id == 0 and slot in SKIN_SLOTS:
        raise ConflictError("Шкаф и постаменты убрать нельзя — на них экспонаты")
    if cosmetic_id:
        cosmetic = await db.get(Cosmetic, cosmetic_id)
        if cosmetic is None or cosmetic.kind != kind:
            raise NotFoundError("Предмет не подходит для этого места")
        if cosmetic_id not in await cosmetic_service.owned_ids(db, user.id):
            raise ConflictError("Сначала купи этот предмет")
    layout = dict(user.hall_layout or {})
    if cosmetic_id is None:
        layout.pop(slot, None)
    else:
        layout[slot] = cosmetic_id
    user.hall_layout = layout or None
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return await view(db, user)
