from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.pack import OpenPackRequest, PackOpenResult, PackOut
from app.schemas.stars import StarsInvoiceCreateOut, StarsInvoiceStatusOut
from app.services import stars_payment_service
from app.services.pack_service import list_available_packs, open_pack

router = APIRouter(prefix="/packs", tags=["packs"])


@router.get("", response_model=list[PackOut])
async def get_packs(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await list_available_packs(db, user.id)


@router.post("/{pack_id}/open", response_model=PackOpenResult)
async def open_pack_endpoint(
    pack_id: int,
    payload: OpenPackRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_rate_limit(f"open_pack:{user.id}", max_calls=10, window_seconds=60)
    return await open_pack(db, user, pack_id, payload.idempotency_key)


@router.post("/{pack_id}/stars-invoice", response_model=StarsInvoiceCreateOut)
async def create_stars_invoice(
    pack_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    check_rate_limit(f"stars_invoice:{user.id}", max_calls=10, window_seconds=60)
    return await stars_payment_service.create_invoice(db, user, pack_id)


@router.get("/stars-invoices/{payload_token}", response_model=StarsInvoiceStatusOut)
async def get_stars_invoice_status(
    payload_token: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await stars_payment_service.get_invoice_status(db, user, payload_token)
