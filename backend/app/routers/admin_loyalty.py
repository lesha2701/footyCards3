from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_db
from app.models.loyalty import LoyaltyReward
from app.models.user import User
from app.services import loyalty_service
from app.services.admin_log_service import log_action
from app.services.game_config_service import get_config

router = APIRouter(prefix="/admin/loyalty", tags=["admin"], dependencies=[Depends(get_current_admin)])


class LoyaltyAdminIn(BaseModel):
    settings: dict


class LoyaltyAdminOut(BaseModel):
    settings: dict
    defaults: dict
    granted: dict[str, int]


async def _out(db: AsyncSession) -> LoyaltyAdminOut:
    config = await get_config(db)
    rows = (await db.execute(
        select(LoyaltyReward.code, func.count()).group_by(LoyaltyReward.code)
    )).all()
    return LoyaltyAdminOut(
        settings=loyalty_service.settings(config), defaults=loyalty_service.DEFAULTS,
        granted={code: count for code, count in rows},
    )


@router.get("", response_model=LoyaltyAdminOut)
async def get_settings(db: AsyncSession = Depends(get_db)):
    return await _out(db)


@router.put("", response_model=LoyaltyAdminOut)
async def update_settings(payload: LoyaltyAdminIn, request: Request, db: AsyncSession = Depends(get_db),
                          admin: User = Depends(get_current_admin)):
    config = await get_config(db)
    old = dict(config.loyalty_settings or {})
    merged = {**old, **loyalty_service.clean_settings(payload.settings)}
    config.loyalty_settings = merged
    db.add(config)
    await log_action(
        db, admin.id, "update_loyalty", "game_config", 1, old_value=old, new_value=merged,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return await _out(db)
