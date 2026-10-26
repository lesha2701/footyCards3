from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_db
from app.models.admin_action import AdminAction
from app.models.card import UserCard
from app.models.pack import PackOpening, StarsInvoice
from app.models.server_error import ServerError
from app.models.trade import TradeOffer
from app.models.user import User
from app.schemas.admin import (
    DashboardChartPoint,
    DashboardOut,
    EconomyReportOut,
    PackExpectedValueOut,
    RecentAdminActionOut,
    ServerErrorGroupOut,
    ServerErrorOut,
    ServerErrorsOut,
)
from app.schemas.admin_analytics import AnalyticsReportOut
from app.schemas.newbie import NewbieFunnelOut
from app.services import admin_analytics_service, admin_economy_service

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

    day_ago = now - timedelta(days=1)
    new_users_24h = (await db.execute(select(func.count(User.id)).where(User.created_at >= day_ago))).scalar_one()
    active_users_24h = (await db.execute(select(func.count(User.id)).where(User.last_seen_at >= day_ago))).scalar_one()
    stars_24h, stars_purchases_24h = (await db.execute(
        select(func.coalesce(func.sum(StarsInvoice.stars_amount), 0), func.count(StarsInvoice.id))
        .where(StarsInvoice.completed_at >= day_ago)
    )).one()
    server_errors_24h = (
        await db.execute(select(func.count(ServerError.id)).where(ServerError.created_at >= day_ago))
    ).scalar_one()

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
        new_users_24h=new_users_24h,
        active_users_24h=active_users_24h,
        stars_24h=int(stars_24h or 0),
        stars_purchases_24h=stars_purchases_24h,
        server_errors_24h=server_errors_24h,
    )


@router.get("/errors", response_model=ServerErrorsOut)
async def get_server_errors(db: AsyncSession = Depends(get_db)):
    """«Ошибки сервера»: the last week's 500s, grouped by endpoint, plus the
    latest ones with their traceback."""
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    groups = (await db.execute(
        select(
            ServerError.method, ServerError.path, func.count(ServerError.id), func.max(ServerError.created_at),
        )
        .where(ServerError.created_at >= week_ago)
        .group_by(ServerError.method, ServerError.path)
        .order_by(func.count(ServerError.id).desc())
        .limit(30)
    )).all()
    recent = (await db.execute(
        select(ServerError).where(ServerError.created_at >= week_ago).order_by(ServerError.id.desc()).limit(40)
    )).scalars().all()
    last_error = {(e.method, e.path): e.error for e in reversed(recent)}
    return ServerErrorsOut(
        groups=[
            ServerErrorGroupOut(method=m, path=p, count=c, last_at=at, last_error=last_error.get((m, p), ""))
            for m, p, c, at in groups
        ],
        recent=[ServerErrorOut.model_validate(e) for e in recent],
    )


@router.get("/economy", response_model=EconomyReportOut)
async def get_economy(days: int = Query(7, ge=1, le=90), db: AsyncSession = Depends(get_db)):
    """Coin inflow/outflow by source and by day, pack and skill-token flow."""
    return await admin_economy_service.economy_report(db, days)


@router.get("/analytics", response_model=AnalyticsReportOut)
async def get_analytics(days: int = Query(30, ge=1, le=90), db: AsyncSession = Depends(get_db)):
    """Activity, retention cohorts, mode popularity, new-player funnel and
    Stars monetization over the last `days` local days (aggregates only)."""
    return await admin_analytics_service.analytics_report(db, days)


@router.get("/newbie-funnel", response_model=NewbieFunnelOut)
async def get_newbie_funnel(days: int = Query(7, ge=1, le=90), db: AsyncSession = Depends(get_db)):
    """«Путь дебютанта»: how many players who started it reached each step."""
    from app.services import newbie_service

    return await newbie_service.funnel(db, days)


@router.get("/packs/{pack_id}/expected-value", response_model=PackExpectedValueOut)
async def get_pack_expected_value(pack_id: int, db: AsyncSession = Depends(get_db)):
    """Expected quick-sell value of one pack vs. its price."""
    return await admin_economy_service.pack_expected_value(db, pack_id)
