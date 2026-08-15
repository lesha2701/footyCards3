from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.user import User
from app.models.wheel import WheelPrize
from app.schemas.wheel import WheelPrizeCreate, WheelPrizeOut, WheelPrizeUpdate
from app.services.admin_log_service import log_action

router = APIRouter(prefix="/admin/wheel", tags=["admin"], dependencies=[Depends(get_current_admin)])


async def _get_prize_or_404(db: AsyncSession, prize_id: int) -> WheelPrize:
    prize = await db.get(WheelPrize, prize_id)
    if not prize:
        raise NotFoundError("Wheel prize not found")
    return prize


@router.get("/prizes", response_model=list[WheelPrizeOut])
async def list_prizes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WheelPrize).order_by(WheelPrize.sort_order))
    return result.scalars().all()


@router.post("/prizes", response_model=WheelPrizeOut)
async def create_prize(payload: WheelPrizeCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    prize = WheelPrize(**payload.model_dump())
    db.add(prize)
    await db.flush()
    await log_action(db, admin.id, "create_wheel_prize", "wheel_prize", prize.id, new_value=payload.model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(prize)
    return WheelPrizeOut.model_validate(prize)


@router.put("/prizes/{prize_id}", response_model=WheelPrizeOut)
async def update_prize(prize_id: int, payload: WheelPrizeUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    prize = await _get_prize_or_404(db, prize_id)
    old_value = WheelPrizeOut.model_validate(prize).model_dump(mode="json")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(prize, key, value)

    db.add(prize)
    await log_action(
        db, admin.id, "update_wheel_prize", "wheel_prize", prize_id, old_value=old_value,
        new_value=payload.model_dump(mode="json", exclude_unset=True),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(prize)
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
    await db.refresh(prize)
    return WheelPrizeOut.model_validate(prize)
