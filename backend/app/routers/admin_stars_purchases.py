from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_admin
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.pack import Pack, StarsInvoice
from app.models.user import User
from app.schemas.admin import StarsDonationSummaryOut, StarsPackPurchaseOut, TopSupporterOut

router = APIRouter(prefix="/admin/stars-purchases", tags=["admin"], dependencies=[Depends(get_current_admin)])


def _base_query():
    return select(StarsInvoice, User, Pack.name).join(User, User.id == StarsInvoice.user_id).join(
        Pack, Pack.id == StarsInvoice.pack_id
    ).where(StarsInvoice.pack_id.is_not(None), StarsInvoice.completed_at.is_not(None))


@router.get("/summary", response_model=StarsDonationSummaryOut)
async def stars_donation_summary(db: AsyncSession = Depends(get_db)):
    """All-time Stars total across every completed purchase — packs *and*
    coin top-ups — unlike the paginated list below, which only lists pack
    purchases."""
    result = await db.execute(
        select(func.coalesce(func.sum(StarsInvoice.stars_amount), 0), func.count(StarsInvoice.id)).where(
            StarsInvoice.completed_at.is_not(None)
        )
    )
    total_stars, total_purchases = result.one()
    return StarsDonationSummaryOut(total_stars=total_stars, total_purchases=total_purchases)


@router.get("/top-supporters", response_model=list[TopSupporterOut])
async def top_supporters(limit: int = 10, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User, func.sum(StarsInvoice.stars_amount), func.count(StarsInvoice.id))
        .options(selectinload(User.active_badge))
        .join(StarsInvoice, StarsInvoice.user_id == User.id)
        .where(StarsInvoice.completed_at.is_not(None))
        .group_by(User.id)
        .order_by(func.sum(StarsInvoice.stars_amount).desc())
        .limit(limit)
    )
    return [
        TopSupporterOut(
            user_id=user.id,
            user_telegram_id=user.telegram_id,
            user_username=user.username,
            user_display_name=user.full_display_name(),
            total_stars=total_stars,
            purchase_count=purchase_count,
        )
        for user, total_stars, purchase_count in result.all()
    ]


@router.get("", response_model=Page[StarsPackPurchaseOut])
async def list_stars_pack_purchases(params: PageParams = Depends(), db: AsyncSession = Depends(get_db)):
    total = (
        await db.execute(select(func.count()).select_from(_base_query().subquery()))
    ).scalar_one()
    result = await db.execute(
        _base_query().order_by(StarsInvoice.completed_at.desc()).offset(params.offset).limit(params.page_size)
    )
    rows = result.all()
    items = [
        StarsPackPurchaseOut(
            id=invoice.id,
            user_id=user.id,
            user_telegram_id=user.telegram_id,
            user_username=user.username,
            user_display_name=user.full_display_name(),
            pack_id=invoice.pack_id,
            pack_name=pack_name,
            stars_amount=invoice.stars_amount,
            telegram_payment_charge_id=invoice.telegram_payment_charge_id,
            completed_at=invoice.completed_at,
        )
        for invoice, user, pack_name in rows
    ]
    return Page.build(items, total, params)
