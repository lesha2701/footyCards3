from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.stars import StarsInvoiceStatusOut
from app.services import academy_service, stars_payment_service

router = APIRouter(prefix="/academy", tags=["academy"])


class KeyRequest(BaseModel):
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


@router.get("")
async def get_academy(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await academy_service.get_state(db, user)


@router.post("/wings/{code}/upgrade")
async def upgrade_wing(code: str, payload: KeyRequest, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    return await academy_service.start_upgrade(db, user, code, payload.idempotency_key)


@router.post("/speedup-invoice")
async def speedup_invoice(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await academy_service.create_speedup_invoice(db, user)


@router.get("/stars-invoices/{payload_token}", response_model=StarsInvoiceStatusOut)
async def speedup_status(payload_token: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stars_payment_service.get_invoice_status(db, user, payload_token)


@router.post("/scout-report")
async def scout_report(payload: KeyRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await academy_service.claim_scout_report(db, user, payload.idempotency_key)
