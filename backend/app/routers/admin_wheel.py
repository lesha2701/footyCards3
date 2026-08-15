from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.dependencies import get_current_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.database import get_db
from app.models.enums import WheelPrizeType
from app.models.pack import Pack
from app.models.user import User
from app.models.wheel import WheelPrize
from app.schemas.wheel import WheelPrizeCreate, WheelPrizeOut, WheelPrizeUpdate
from app.services.admin_log_service import log_action

router = APIRouter(prefix="/admin/wheel", tags=["admin"], dependencies=[Depends(get_current_admin)])

# WheelPrize.pack is lazy="joined", but Pack.rarity_probabilities (needed by
# PackOut, nested in WheelPrizeOut.pack) is not — without this explicit
# option, serializing a pack-type prize triggers an async lazy-load outside
# any awaited context (MissingGreenlet), the same pitfall pack_service.py /
# admin_packs.py already work around for plain Pack queries.
_PACK_PROBABILITIES = joinedload(WheelPrize.pack).joinedload(Pack.rarity_probabilities)


_REQUIRED_FIELD_BY_TYPE = {
    WheelPrizeType.coins: "coins_amount",
    WheelPrizeType.pack: "pack_id",
    WheelPrizeType.card_rarity: "card_rarity",
    WheelPrizeType.badge: "badge_id",
}


def _validate_prize_fields(prize: WheelPrize) -> None:
    """Enforces "exactly one of coins_amount/pack_id/card_rarity/badge_id
    matches prize_type" against the fully-resolved object (i.e. after
    applying whatever fields this specific request did or didn't include) —
    a malformed row (e.g. prize_type=card_rarity with card_rarity=null)
    causes real damage when rolled: a coins-type prize with a null amount
    crashes, a pack-type with a null pack_id 404s, a badge-type with a null
    badge_id violates a NOT NULL constraint, and a card_rarity-type with a
    null card_rarity silently falls through to "any active player" and
    grants a random common card while claiming to be a rare/epic/legendary
    prize."""
    required_field = _REQUIRED_FIELD_BY_TYPE[prize.prize_type]
    if getattr(prize, required_field) is None:
        raise ConflictError(f"prize_type '{prize.prize_type.value}' requires {required_field} to be set")


async def _get_prize_or_404(db: AsyncSession, prize_id: int) -> WheelPrize:
    result = await db.execute(select(WheelPrize).where(WheelPrize.id == prize_id).options(_PACK_PROBABILITIES))
    prize = result.unique().scalar_one_or_none()
    if not prize:
        raise NotFoundError("Wheel prize not found")
    return prize


@router.get("/prizes", response_model=list[WheelPrizeOut])
async def list_prizes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WheelPrize).order_by(WheelPrize.sort_order).options(_PACK_PROBABILITIES))
    return result.unique().scalars().all()


@router.post("/prizes", response_model=WheelPrizeOut)
async def create_prize(payload: WheelPrizeCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    prize = WheelPrize(**payload.model_dump())
    _validate_prize_fields(prize)
    db.add(prize)
    await db.flush()
    await log_action(db, admin.id, "create_wheel_prize", "wheel_prize", prize.id, new_value=payload.model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    await db.commit()
    prize = await _get_prize_or_404(db, prize.id)
    return WheelPrizeOut.model_validate(prize)


@router.put("/prizes/{prize_id}", response_model=WheelPrizeOut)
async def update_prize(prize_id: int, payload: WheelPrizeUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    prize = await _get_prize_or_404(db, prize_id)
    old_value = WheelPrizeOut.model_validate(prize).model_dump(mode="json")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(prize, key, value)
    _validate_prize_fields(prize)

    db.add(prize)
    await log_action(
        db, admin.id, "update_wheel_prize", "wheel_prize", prize_id, old_value=old_value,
        new_value=payload.model_dump(mode="json", exclude_unset=True),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    prize = await _get_prize_or_404(db, prize_id)
    return WheelPrizeOut.model_validate(prize)


@router.delete("/prizes/{prize_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prize(prize_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    prize = await _get_prize_or_404(db, prize_id)
    await log_action(db, admin.id, "delete_wheel_prize", "wheel_prize", prize_id, old_value=WheelPrizeOut.model_validate(prize).model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    await db.delete(prize)
    await db.commit()


@router.post("/prizes/{prize_id}/toggle-active", response_model=WheelPrizeOut)
async def toggle_prize_active(prize_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    prize = await _get_prize_or_404(db, prize_id)
    prize.is_active = not prize.is_active
    db.add(prize)
    await log_action(db, admin.id, "toggle_wheel_prize_active", "wheel_prize", prize_id, new_value={"is_active": prize.is_active}, ip_address=request.client.host if request.client else None)
    await db.commit()
    prize = await _get_prize_or_404(db, prize_id)
    return WheelPrizeOut.model_validate(prize)
