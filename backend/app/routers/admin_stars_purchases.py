from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.pack import Pack, StarsInvoice
from app.models.user import User
from app.schemas.admin import StarsPackPurchaseOut

router = APIRouter(prefix="/admin/stars-purchases", tags=["admin"], dependencies=[Depends(get_current_admin)])


def _base_query():
    return select(StarsInvoice, User, Pack.name).join(User, User.id == StarsInvoice.user_id).join(
        Pack, Pack.id == StarsInvoice.pack_id
    ).where(StarsInvoice.pack_id.is_not(None), StarsInvoice.completed_at.is_not(None))


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
