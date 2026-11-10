from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_db
from app.models.user import User
from app.schemas.admin_antifraud import AntifraudBanIn, AntifraudBanOut, AntifraudScanOut, BotSuspectOut, ClearedIn, RewardsBlockIn, WatchIn
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


@router.get("/bots", response_model=list[BotSuspectOut])
async def bots(
    days: int = Query(7, ge=1, le=30), min_games: int = Query(150, ge=10, le=100_000),
    cleared: bool = Query(False), db: AsyncSession = Depends(get_db),
):
    """Accounts that play around the clock (no sleep) — likely scripts.
    `cleared=true`: the ones an admin marked «Проверен, не бот» instead."""
    return await admin_antifraud_service.bot_suspects(db, days=days, min_games=min_games, cleared=cleared)


@router.post("/rewards-block")
async def rewards_block(
    payload: RewardsBlockIn, request: Request,
    admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    """«Без наград за игры» on / off for many accounts."""
    changed = await admin_antifraud_service.set_rewards_blocked(db, payload.user_ids, payload.blocked)
    await log_action(
        db, admin.id, "antifraud_rewards_block", "user", None,
        new_value={"blocked": payload.blocked, "count": len(changed), "user_ids": changed[:500]},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"changed": len(changed), "user_ids": changed}


@router.post("/cleared")
async def mark_cleared(
    payload: ClearedIn, request: Request,
    admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    """«Проверен, не бот» on / off for many accounts."""
    changed = await admin_antifraud_service.set_cleared(db, payload.user_ids, payload.cleared)
    await log_action(
        db, admin.id, "antifraud_cleared", "user", None,
        new_value={"cleared": payload.cleared, "count": len(changed), "user_ids": changed[:500]},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"changed": len(changed), "user_ids": changed}


@router.post("/watch")
async def watch(
    payload: WatchIn, request: Request,
    admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    """«Под наблюдением» («Ты здесь?» и «усталость») on / off for many accounts."""
    changed = await admin_antifraud_service.set_watched(db, payload.user_ids, payload.watched)
    await log_action(
        db, admin.id, "antifraud_watch", "user", None,
        new_value={"watched": payload.watched, "count": len(changed), "user_ids": changed[:500]},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"changed": len(changed), "user_ids": changed}


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
