from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.stars import StarsInvoiceStatusOut
from app.services import club_base_service, stars_payment_service

router = APIRouter(prefix="/club-base", tags=["club-base"])


class KeyRequest(BaseModel):
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class LookRequest(BaseModel):
    seats: Optional[str] = Field(default=None, max_length=16)
    roof: Optional[Literal["none", "canopy", "full"]] = None
    lights: Optional[bool] = None
    screen: Optional[bool] = None


@router.get("")
async def get_base(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_base_service.get_state(db, user)


@router.post("/buildings/{code}/upgrade")
async def upgrade_building(code: str, payload: KeyRequest, db: AsyncSession = Depends(get_db),
                           user: User = Depends(get_current_user)):
    return await club_base_service.start_upgrade(db, user, code, payload.idempotency_key)


@router.post("/income/claim")
async def claim_income(payload: KeyRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_base_service.claim_income(db, user, payload.idempotency_key)


@router.put("/stadium/look")
async def set_look(payload: LookRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_base_service.set_look(db, user, payload.model_dump(exclude_none=True))


@router.post("/speedup-invoice")
async def speedup_invoice(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_base_service.create_speedup_invoice(db, user)


@router.get("/stars-invoices/{payload_token}", response_model=StarsInvoiceStatusOut)
async def speedup_status(payload_token: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stars_payment_service.get_invoice_status(db, user, payload_token)
