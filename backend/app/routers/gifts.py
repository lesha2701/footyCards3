from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.gift import GiftClaimResult, GiftOut, GiftSendIn, GiftSetOut
from app.schemas.stars import StarsInvoiceCreateOut, StarsInvoiceStatusOut
from app.services import gift_service, stars_payment_service

router = APIRouter(prefix="/gifts", tags=["gifts"])


@router.get("/sets", response_model=list[GiftSetOut])
async def list_gift_sets(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await gift_service.list_active_gift_sets(db)


@router.post("/invoice", response_model=StarsInvoiceCreateOut)
async def create_gift_invoice(
    payload: GiftSendIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await stars_payment_service.create_gift_invoice(
        db, user, payload.gift_set_id, payload.recipient_id, payload.message
    )


@router.get("/stars-invoices/{payload_token}", response_model=StarsInvoiceStatusOut)
async def gift_invoice_status(
    payload_token: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await stars_payment_service.get_invoice_status(db, user, payload_token)


@router.get("/mine", response_model=list[GiftOut])
async def list_my_gifts(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await gift_service.list_my_gifts(db, user)


@router.post("/{gift_id}/claim", response_model=GiftClaimResult)
async def claim_gift(gift_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await gift_service.claim_gift(db, user, gift_id)
