from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.stars import StarsInvoiceStatusOut
from app.services import prospect_life, prospect_service, stars_payment_service

router = APIRouter(prefix="/prospect", tags=["prospect"])


class CreateRequest(BaseModel):
    name: str = Field(max_length=40)
    number: int = Field(ge=1, le=99)
    # Ignored: he is a universal player until the coach's offer.
    position: Optional[str] = Field(default=None, max_length=8)
    foot: str = Field(default="right", max_length=8)
    appearance: dict = Field(default_factory=dict)


class UpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=40)
    number: Optional[int] = Field(default=None, ge=1, le=99)
    position: Optional[str] = Field(default=None, max_length=8)
    foot: Optional[str] = Field(default=None, max_length=8)
    appearance: Optional[dict] = None


class TrainRequest(BaseModel):
    drill: str = Field(max_length=16)


class StoryRequest(BaseModel):
    code: str = Field(max_length=32)
    option: int = Field(ge=0, le=5)


class MentorRequest(BaseModel):
    card_id: Optional[int] = None


class EquipRequest(BaseModel):
    kind: str = Field(max_length=16)
    code: Optional[str] = Field(default=None, max_length=32)


class InvoiceRequest(BaseModel):
    purchase: str = Field(max_length=24)


@router.get("")
async def get_prospect(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await prospect_service.get_view(db, user)


@router.post("")
async def create_prospect(payload: CreateRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await prospect_service.create(db, user, payload.name, payload.number, payload.position, payload.foot, payload.appearance)


@router.patch("")
async def update_prospect(payload: UpdateRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await prospect_service.update(db, user, payload.name, payload.number, payload.position, payload.foot, payload.appearance)


class PositionRequest(BaseModel):
    position: str = Field(max_length=8)


@router.post("/position")
async def choose_position(payload: PositionRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await prospect_service.choose_position(db, user, payload.position)


@router.post("/train")
async def train(payload: TrainRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"prospect_train:{user.id}", max_calls=10, window_seconds=60)
    return await prospect_service.train(db, user, payload.drill)


@router.post("/story")
async def story(payload: StoryRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"prospect_story:{user.id}", max_calls=10, window_seconds=60)
    return await prospect_service.answer_story(db, user, payload.code, payload.option)


@router.put("/mentor")
async def mentor(payload: MentorRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await prospect_service.set_mentor(db, user, payload.card_id)


@router.post("/cosmetics/{code}/buy")
async def buy_cosmetic(code: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await prospect_service.buy_cosmetic(db, user, code)


@router.put("/cosmetics/equip")
async def equip(payload: EquipRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await prospect_service.equip_cosmetic(db, user, payload.kind, payload.code)


@router.post("/stars-invoice")
async def stars_invoice(payload: InvoiceRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"prospect_invoice:{user.id}", max_calls=10, window_seconds=60)
    return await prospect_service.create_stars_invoice(db, user, payload.purchase)


@router.get("/stars-invoices/{payload_token}", response_model=StarsInvoiceStatusOut)
async def invoice_status(payload_token: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stars_payment_service.get_invoice_status(db, user, payload_token)


# --- life: talents, graduation, duels (prospect_life) ---

class SpecRequest(BaseModel):
    code: str = Field(max_length=16)


class DuelRequest(BaseModel):
    friend_id: int


@router.post("/spec")
async def choose_spec(payload: SpecRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await prospect_life.choose_spec(db, user, payload.code)


@router.post("/graduate")
async def graduate(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"prospect_graduate:{user.id}", max_calls=5, window_seconds=60)
    return await prospect_life.graduate(db, user)


@router.post("/duels")
async def create_duel(payload: DuelRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"prospect_duel:{user.id}", max_calls=10, window_seconds=60)
    return await prospect_life.create_duel(db, user, payload.friend_id)
