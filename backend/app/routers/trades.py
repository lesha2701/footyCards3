from typing import Literal, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.enums import TradeStatus
from app.models.user import User
from app.schemas.trade import TradeAcceptOut, TradeCreateRequest, TradeOfferOut, TradeRulesOut
from app.services import trade_guard_service, trade_service
from app.services.game_config_service import get_config

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("/rules", response_model=TradeRulesOut)
async def get_trade_rules(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await trade_guard_service.rules_for(db, user, await get_config(db))


@router.get("/offers", response_model=list[TradeOfferOut])
async def list_trade_offers(
    status: Optional[TradeStatus] = None,
    direction: Optional[Literal["incoming", "outgoing"]] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await trade_service.list_offers(db, user, status, direction)


@router.post("/offers", response_model=TradeOfferOut)
async def create_trade_offer(
    payload: TradeCreateRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    await check_rate_limit(f"create_trade:{user.id}", max_calls=10, window_seconds=60)
    return await trade_service.create_offer(db, user, payload)


@router.get("/offers/{offer_id}", response_model=TradeOfferOut)
async def get_trade_offer(offer_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await trade_service.get_offer(db, user, offer_id)


@router.post("/offers/{offer_id}/cancel", response_model=TradeOfferOut)
async def cancel_trade_offer(offer_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await trade_service.cancel_offer(db, user, offer_id)


@router.post("/offers/{offer_id}/accept", response_model=TradeAcceptOut)
async def accept_trade_offer(offer_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"accept_trade:{user.id}", max_calls=20, window_seconds=60)
    return await trade_service.accept_offer(db, user, offer_id)


@router.post("/offers/{offer_id}/reject", response_model=TradeOfferOut)
async def reject_trade_offer(offer_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await trade_service.reject_offer(db, user, offer_id)
