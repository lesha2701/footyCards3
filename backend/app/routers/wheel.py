from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.stars import StarsInvoiceCreateOut, StarsInvoiceStatusOut
from app.schemas.wheel import WheelSpinResultOut, WheelStatusOut
from app.services import stars_payment_service, wheel_service

router = APIRouter(prefix="/wheel", tags=["wheel"])


@router.get("/status", response_model=WheelStatusOut)
async def get_status(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await wheel_service.get_status(db, user)


@router.post("/spin/free", response_model=WheelSpinResultOut)
async def spin_free(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await wheel_service.spin_free(db, user)


@router.post("/spin/coins", response_model=WheelSpinResultOut)
async def spin_paid_coins(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await wheel_service.spin_paid_coins(db, user)


@router.post("/spin/stars-invoice", response_model=StarsInvoiceCreateOut)
async def create_stars_spin_invoice(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await wheel_service.create_spin_invoice(db, user)


@router.get("/stars-invoices/{payload_token}", response_model=StarsInvoiceStatusOut)
async def get_stars_spin_invoice_status(
    payload_token: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await stars_payment_service.get_invoice_status(db, user, payload_token)
