from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.stars import StarsInvoiceStatusOut
from app.services import path_service, stars_payment_service
from app.services.game_config_service import get_config
from app.services.path_talent_catalog import TALENTS

router = APIRouter(prefix="/path", tags=["path"])


class BuyAttemptRequest(BaseModel):
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


@router.get("/catalog")
async def get_catalog(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    """Talents (both levels, where each one works) and stages — for the
    «Академия» info screen and the card badges."""
    config = await get_config(db)
    catalog = await path_service.load_catalog(db)
    return {
        "title": config.path_title,
        "enabled": bool(config.path_enabled),
        "talent_cap": int(config.path_talent_cap),
        "stages": [
            {"index": s.stage_index, "name": s.name, "max_rating": s.max_rating, "talent_level": s.talent_level}
            for s in catalog.stages
        ],
        "talents": [
            path_service.talent_out(code, 2, catalog, config)
            for code in sorted(TALENTS, key=lambda c: (catalog.talents[c].sort_order if c in catalog.talents else 0, c))
        ],
    }


@router.get("/cards/{card_id}")
async def get_card_path(card_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await path_service.get_state(db, user, card_id)


@router.post("/cards/{card_id}/buy-attempt")
async def buy_attempt(
    card_id: int, payload: BuyAttemptRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await path_service.buy_attempt_with_coins(db, user, card_id, payload.idempotency_key)


@router.post("/cards/{card_id}/stars-invoice")
async def create_stars_invoice(card_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await path_service.create_stars_invoice(db, user, card_id)


@router.get("/stars-invoices/{payload_token}", response_model=StarsInvoiceStatusOut)
async def get_stars_invoice_status(payload_token: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stars_payment_service.get_invoice_status(db, user, payload_token)
