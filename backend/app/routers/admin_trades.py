from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import Page, PageParams
from app.core.timeutil import app_timezone
from app.database import get_db
from app.models.enums import TradeStatus
from app.models.trade import TradeOffer
from app.models.user import User
from app.schemas.trade import TradeOfferOut
from app.services.admin_log_service import log_action
from app.services.trade_service import hydrate_offer, unlock_trade_cards

router = APIRouter(prefix="/admin/trades", tags=["admin"], dependencies=[Depends(get_current_admin)])


def _local_day_start(day: date) -> datetime:
    """Start of a local calendar day (settings.timezone) as an aware UTC datetime."""
    return datetime.combine(day, time.min, tzinfo=app_timezone()).astimezone(timezone.utc)


@router.get("", response_model=Page[TradeOfferOut])
async def list_all_trades(
    status: Optional[TradeStatus] = None,
    username: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """All trade offers, newest first, paginated. date_from / date_to are
    inclusive local calendar days (settings.timezone) on created_at."""
    query = select(TradeOffer)
    if status:
        query = query.where(TradeOffer.status == status)
    if date_from:
        query = query.where(TradeOffer.created_at >= _local_day_start(date_from))
    if date_to:
        query = query.where(TradeOffer.created_at < _local_day_start(date_to + timedelta(days=1)))
    if username:
        matching_user_ids = (
            await db.execute(select(User.id).where(User.username.ilike(f"%{username}%")))
        ).scalars().all()
        if not matching_user_ids:
            return Page.build([], 0, params)
        query = query.where(
            or_(TradeOffer.sender_id.in_(matching_user_ids), TradeOffer.receiver_id.in_(matching_user_ids))
        )
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    offers = (
        await db.execute(
            query.order_by(TradeOffer.created_at.desc(), TradeOffer.id.desc()).offset(params.offset).limit(params.page_size)
        )
    ).scalars().all()
    return Page.build([await hydrate_offer(db, o) for o in offers], total, params)


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
