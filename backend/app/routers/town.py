from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.stars import StarsInvoiceStatusOut
from app.services import stars_payment_service, town_season_service, town_service, town_social_service

router = APIRouter(prefix="/town", tags=["town"])


class KeyRequest(BaseModel):
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class SellRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=1000)


class SettleRequest(BaseModel):
    district: Optional[str] = Field(default=None, max_length=16)


class RenameRequest(BaseModel):
    name: str = Field(max_length=64)


@router.get("")
async def get_town(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await town_service.get_state(db, user)


@router.post("/houses/{district}/{code}/buy")
async def buy_house(district: str, code: str, payload: KeyRequest, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    return await town_service.buy_house(db, user, district, code, payload.idempotency_key)


@router.post("/income/claim")
async def claim_income(payload: KeyRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await town_service.claim_income(db, user, payload.idempotency_key)


@router.post("/hotel/buy")
async def buy_hotel(payload: KeyRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await town_service.buy_hotel(db, user, payload.idempotency_key)


@router.post("/decor/{code}/buy")
async def buy_decor(code: str, payload: KeyRequest, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    return await town_service.buy_decor(db, user, code, payload.idempotency_key)


@router.post("/unlock")
async def unlock(payload: KeyRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await town_service.unlock(db, user, payload.idempotency_key)


@router.get("/residents")
async def residents(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await town_service.album(db, user)


@router.get("/quests")
async def quests(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await town_social_service.quests(db, user)


@router.post("/quests/{quest_id}/claim")
async def claim_quest(quest_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await town_social_service.claim_quest(db, user, quest_id)


@router.get("/guests")
async def guests(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await town_social_service.guests(db, user)


@router.get("/season")
async def season(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await town_season_service.shop(db, user)


@router.post("/season/{code}/invoice")
async def season_invoice(code: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await town_season_service.create_invoice(db, user, code)


@router.get("/week")
async def week(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await town_social_service.week_ranking(db, user)


@router.get("/visit/{owner_id}")
async def visit(owner_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await town_social_service.visit(db, user, owner_id)


@router.post("/visit/{owner_id}/like")
async def like(owner_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await town_social_service.like(db, user, owner_id)


@router.post("/visit/{owner_id}/gift")
async def gift(owner_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await town_social_service.gift(db, user, owner_id)


@router.post("/residents/{resident_id}/settle")
async def settle(resident_id: int, payload: SettleRequest, db: AsyncSession = Depends(get_db),
                 user: User = Depends(get_current_user)):
    return await town_service.settle_resident(db, user, resident_id, payload.district)


@router.post("/residents/{resident_id}/sell-spare")
async def sell_spare(resident_id: int, payload: SellRequest, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    return await town_service.sell_spare(db, user, resident_id, payload.count)


@router.post("/rename-invoice")
async def rename_invoice(payload: RenameRequest, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    return await town_service.create_rename_invoice(db, user, payload.name)


@router.get("/stars-invoices/{payload_token}", response_model=StarsInvoiceStatusOut)
async def invoice_status(payload_token: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stars_payment_service.get_invoice_status(db, user, payload_token)
