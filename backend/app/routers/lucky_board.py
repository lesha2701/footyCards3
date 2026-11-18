from typing import Optional

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.lucky_board import LuckyBoardSpinOut, LuckyBoardStatusOut
from app.schemas.stars import StarsInvoiceCreateOut
from app.services import lucky_board_service, shop_product_service

router = APIRouter(prefix="/lucky-board", tags=["lucky-board"])


@router.get("/status", response_model=LuckyBoardStatusOut)
async def get_status(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await lucky_board_service.get_status(db, user)


@router.post("/spin", response_model=LuckyBoardSpinOut)
async def spin(
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await lucky_board_service.spin(db, user, idempotency_key)


@router.post("/stars-invoice", response_model=StarsInvoiceCreateOut)
async def create_stars_invoice(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await shop_product_service.create_invoice(db, user, *await lucky_board_service.stars_order(db, user))
