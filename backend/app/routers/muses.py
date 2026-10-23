from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.muse import MuseActivateIn, MuseGiftIn, MuseGiftInvoiceIn, MuseSellSpareIn
from app.schemas.stars import StarsInvoiceCreateOut
from app.services import muse_service, shop_product_service

router = APIRouter(prefix="/muses", tags=["muses"])


@router.get("")
async def album(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await muse_service.album(db, user)


@router.post("/active")
async def set_active(payload: MuseActivateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await muse_service.set_active(db, user, payload.muse_id)


@router.post("/daily/claim")
async def claim_daily(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await muse_service.claim_daily(db, user)


@router.post("/date/start")
async def start_date(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Today's «Свидание»: the random mini-game to open with ?muse=1."""
    return await muse_service.start_date(db, user)


@router.post("/{muse_id}/sell-spare")
async def sell_spare(
    muse_id: int, payload: MuseSellSpareIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await muse_service.sell_spare(db, user, muse_id, payload.count)


@router.post("/{muse_id}/gifts")
async def buy_gift(
    muse_id: int, payload: MuseGiftIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await muse_service.buy_accessory(db, user, muse_id, payload.accessory_id, payload.idempotency_key)


@router.post("/{muse_id}/gifts/stars-invoice", response_model=StarsInvoiceCreateOut)
async def gift_invoice(
    muse_id: int, payload: MuseGiftInvoiceIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await shop_product_service.create_invoice(
        db, user, *await muse_service.stars_order(db, user, muse_id, payload.accessory_id),
    )
