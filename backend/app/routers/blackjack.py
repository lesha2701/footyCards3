from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.blackjack import BlackjackActionOut, BlackjackStatusOut
from app.schemas.stars import StarsInvoiceCreateOut, StarsInvoiceStatusOut
from app.services import blackjack_service, stars_payment_service

router = APIRouter(prefix="/blackjack", tags=["blackjack"])


@router.get("/status", response_model=BlackjackStatusOut)
async def get_status(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await blackjack_service.get_status(db, user)


@router.post("/start", response_model=BlackjackActionOut)
async def start_match(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await blackjack_service.start_match(db, user)


@router.post("/matches/{match_id}/hit", response_model=BlackjackActionOut)
async def hit(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await blackjack_service.hit(db, user, match_id)


@router.post("/matches/{match_id}/stand", response_model=BlackjackActionOut)
async def stand(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await blackjack_service.stand(db, user, match_id)


@router.post("/stars-invoice", response_model=StarsInvoiceCreateOut)
async def create_stars_invoice(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await blackjack_service.create_entry_invoice(db, user)


@router.get("/stars-invoices/{payload_token}", response_model=StarsInvoiceStatusOut)
async def get_stars_invoice_status(
    payload_token: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await stars_payment_service.get_invoice_status(db, user, payload_token)
