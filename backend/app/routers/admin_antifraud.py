from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_db
from app.models.user import User
from app.schemas.admin_antifraud import AntifraudBanIn, AntifraudBanOut, AntifraudScanOut
from app.services import admin_antifraud_service
from app.services.admin_log_service import log_action

router = APIRouter(prefix="/admin/antifraud", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("/scan", response_model=AntifraudScanOut)
async def scan(
    min_senders: int = Query(20, ge=2, le=1000),
    days: int = Query(120, ge=1, le=730),
    burst_min: int = Query(30, ge=5, le=10000),
    db: AsyncSession = Depends(get_db),
):
    """Coin-farming networks: hubs, the accounts that fed them, registration bursts."""
    return await admin_antifraud_service.scan(db, min_senders=min_senders, days=days, burst_min=burst_min)


@router.post("/ban", response_model=AntifraudBanOut)
async def ban(
    payload: AntifraudBanIn, request: Request,
    admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    """Bans (and trade-bans) the given accounts; admins / already banned are skipped."""
    banned = await admin_antifraud_service.ban_users(db, payload.user_ids)
    await log_action(
        db, admin.id, "antifraud_ban", "user", None,
        new_value={"count": len(banned), "user_ids": banned[:500]},
        ip_address=request.client.host if request.client else None, extra=payload.reason,
    )
    await db.commit()
    return AntifraudBanOut(banned=len(banned), user_ids=banned)
