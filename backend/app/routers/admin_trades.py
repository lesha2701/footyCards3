from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.database import get_db
from app.models.enums import TradeStatus
from app.models.trade import TradeOffer
from app.models.user import User
from app.schemas.trade import TradeOfferOut
from app.services.admin_log_service import log_action
from app.services.trade_service import hydrate_offer, unlock_trade_cards

router = APIRouter(prefix="/admin/trades", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=list[TradeOfferOut])
async def list_all_trades(status: Optional[TradeStatus] = None, db: AsyncSession = Depends(get_db)):
    query = select(TradeOffer).order_by(TradeOffer.created_at.desc()).limit(200)
    if status:
        query = query.where(TradeOffer.status == status)
    offers = (await db.execute(query)).scalars().all()
    return [await hydrate_offer(db, o) for o in offers]


@router.get("/{offer_id}", response_model=TradeOfferOut)
async def get_trade(offer_id: int, db: AsyncSession = Depends(get_db)):
    offer = await db.get(TradeOffer, offer_id)
    if not offer:
        raise NotFoundError("Trade offer not found")
    return await hydrate_offer(db, offer)


@router.post("/{offer_id}/force-cancel", response_model=TradeOfferOut)
async def force_cancel_trade(offer_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    offer = await db.get(TradeOffer, offer_id)
    if not offer:
        raise NotFoundError("Trade offer not found")
    if offer.status != TradeStatus.pending:
        raise ConflictError("Only pending trades can be force-cancelled")

    offer.status = TradeStatus.cancelled
    offer.resolved_at = datetime.now(timezone.utc)
    await unlock_trade_cards(db, offer.id)
    db.add(offer)

    await log_action(
        db, admin.id, "force_cancel_trade", "trade_offer", offer_id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return await hydrate_offer(db, offer)
