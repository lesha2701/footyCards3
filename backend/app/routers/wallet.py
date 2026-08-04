from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.stars import (
    CoinPackageOut,
    StarsCoinInvoiceCreate,
    StarsInvoiceCreateOut,
    StarsInvoiceStatusOut,
)
from app.services import stars_payment_service

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("/coin-packages", response_model=list[CoinPackageOut])
async def get_coin_packages(db: AsyncSession = Depends(get_db)):
    return await stars_payment_service.list_active_coin_packages(db)


@router.post("/stars-invoice", response_model=StarsInvoiceCreateOut)
async def create_coin_invoice(
    payload: StarsCoinInvoiceCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    check_rate_limit(f"stars_coin_invoice:{user.id}", max_calls=10, window_seconds=60)
    return await stars_payment_service.create_coin_invoice(db, user, payload.coin_package_id)


@router.get("/stars-invoices/{payload_token}", response_model=StarsInvoiceStatusOut)
async def get_coin_invoice_status(
    payload_token: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await stars_payment_service.get_invoice_status(db, user, payload_token)
