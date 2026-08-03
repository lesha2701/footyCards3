from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import verify_internal_secret
from app.database import get_db
from app.schemas.stars import (
    StarsInvoiceStatusOut,
    StarsPaymentDeliverIn,
    StarsPreCheckoutValidateIn,
    StarsPreCheckoutValidateOut,
)
from app.services import stars_payment_service

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(verify_internal_secret)])


@router.post("/stars-payments/pre-checkout", response_model=StarsPreCheckoutValidateOut)
async def pre_checkout(payload: StarsPreCheckoutValidateIn, db: AsyncSession = Depends(get_db)):
    ok, error_message = await stars_payment_service.validate_pre_checkout(
        db, payload.payload_token, payload.total_amount
    )
    return StarsPreCheckoutValidateOut(ok=ok, error_message=error_message or None)


@router.post("/stars-payments/deliver", response_model=StarsInvoiceStatusOut)
async def deliver(payload: StarsPaymentDeliverIn, db: AsyncSession = Depends(get_db)):
    return await stars_payment_service.deliver_payment(
        db, payload.payload_token, payload.telegram_user_id, payload.telegram_payment_charge_id, payload.total_amount
    )
