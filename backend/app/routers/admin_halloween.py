from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import ConflictError
from app.database import get_db
from app.models.user import User
from app.schemas.halloween import HalloweenAdminIn, HalloweenAdminOut
from app.services import halloween_service
from app.services.admin_log_service import log_action
from app.services.game_config_service import get_config

router = APIRouter(prefix="/admin/halloween", tags=["admin"], dependencies=[Depends(get_current_admin)])


async def _out(db: AsyncSession) -> HalloweenAdminOut:
    config = await get_config(db)
    start, end = halloween_service.window(config)
    return HalloweenAdminOut(
        enabled=config.halloween_enabled, starts_at=start, ends_at=end,
        settings=halloween_service.settings_of(config), defaults=halloween_service.DEFAULT_SETTINGS,
        stats=await halloween_service.admin_stats(db, config),
    )


@router.get("", response_model=HalloweenAdminOut)
async def get_settings(db: AsyncSession = Depends(get_db)):
    return await _out(db)


@router.put("", response_model=HalloweenAdminOut)
async def update_settings(payload: HalloweenAdminIn, request: Request, db: AsyncSession = Depends(get_db),
                          admin: User = Depends(get_current_admin)):
    config = await get_config(db)
    old = {"enabled": config.halloween_enabled, "settings": config.halloween_settings}
    if payload.enabled is not None:
        config.halloween_enabled = payload.enabled
    if payload.starts_at is not None:
        config.halloween_starts_at = payload.starts_at
    if payload.ends_at is not None:
        config.halloween_ends_at = payload.ends_at
    start, end = halloween_service.window(config)
    if end <= start:
        raise ConflictError("Конец ивента должен быть позже начала")
    if payload.settings is not None:
        merged = dict(config.halloween_settings or {})
        merged.update(halloween_service.validate_settings(payload.settings))
        config.halloween_settings = merged
    db.add(config)
    await log_action(
        db, admin.id, "update_halloween", "game_config", 1, old_value=old,
        new_value=payload.model_dump(mode="json", exclude_unset=True),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(config)
    return await _out(db)
