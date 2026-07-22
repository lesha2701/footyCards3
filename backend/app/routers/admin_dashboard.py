from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_db
from app.models.admin_action import AdminAction
from app.models.card import UserCard
from app.models.pack import PackOpening
from app.models.trade import TradeOffer
from app.models.user import User
from app.schemas.admin import DashboardChartPoint, DashboardOut, RecentAdminActionOut

router = APIRouter(prefix="/admin/dashboard", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=DashboardOut)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    fortnight_ago = now - timedelta(days=14)

    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()
    active_users_7d = (
        await db.execute(select(func.count(User.id)).where(User.last_seen_at >= week_ago))
    ).scalar_one()
    total_packs_opened = (await db.execute(select(func.count(PackOpening.id)))).scalar_one()
    total_cards_issued = (await db.execute(select(func.count(UserCard.id)))).scalar_one()
    total_trades = (await db.execute(select(func.count(TradeOffer.id)))).scalar_one()
    coins_in_circulation = (await db.execute(select(func.coalesce(func.sum(User.balance), 0)))).scalar_one()

    reg_rows = (
        await db.execute(
            select(func.date(User.created_at), func.count(User.id))
            .where(User.created_at >= fortnight_ago)
            .group_by(func.date(User.created_at))
            .order_by(func.date(User.created_at))
        )
    ).all()
    registrations_by_day = [DashboardChartPoint(date=str(d), count=c) for d, c in reg_rows]

    pack_rows = (
        await db.execute(
            select(func.date(PackOpening.created_at), func.count(PackOpening.id))
            .where(PackOpening.created_at >= fortnight_ago)
            .group_by(func.date(PackOpening.created_at))
            .order_by(func.date(PackOpening.created_at))
        )
    ).all()
    pack_openings_by_day = [DashboardChartPoint(date=str(d), count=c) for d, c in pack_rows]

    recent_actions_rows = (
        await db.execute(select(AdminAction).order_by(AdminAction.created_at.desc()).limit(20))
    ).scalars().all()

    return DashboardOut(
        total_users=total_users,
        active_users_7d=active_users_7d,
        total_packs_opened=total_packs_opened,
        total_cards_issued=total_cards_issued,
        total_trades=total_trades,
        coins_in_circulation=coins_in_circulation,
        registrations_by_day=registrations_by_day,
        pack_openings_by_day=pack_openings_by_day,
        recent_actions=[RecentAdminActionOut.model_validate(a) for a in recent_actions_rows],
    )
