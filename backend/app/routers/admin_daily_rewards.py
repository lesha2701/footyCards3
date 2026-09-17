from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import ConflictError
from app.database import get_db
from app.models.daily_reward import DailyRewardOption
from app.models.pack import Pack
from app.models.user import User
from app.schemas.daily_reward import DailyRewardOptionOut, DailyRewardOptionsUpdate
from app.services.admin_log_service import log_action
from app.services.daily_reward_service import get_day_options

router = APIRouter(prefix="/admin/daily-reward-options", tags=["admin"], dependencies=[Depends(get_current_admin)])


async def _validate_options(db: AsyncSession, options: list) -> None:
    for opt in options:
        if not (1 <= opt.day <= 7):
            raise ConflictError(f"day must be between 1 and 7 (got {opt.day})")
        if opt.coins < 0:
            raise ConflictError(f"coins must be >= 0 (day {opt.day}, option {opt.option_index})")
        if opt.free_pack_slug:
            pack = (await db.execute(select(Pack).where(Pack.slug == opt.free_pack_slug))).scalar_one_or_none()
            if not pack:
                raise ConflictError(f"Unknown pack slug '{opt.free_pack_slug}' (day {opt.day})")
    days_present = {opt.day for opt in options}
    missing = sorted(set(range(1, 8)) - days_present)
    if missing:
        raise ConflictError(f"Every day 1-7 needs at least one reward option — missing: {missing}")


@router.get("", response_model=list[DailyRewardOptionOut])
async def list_daily_reward_options(db: AsyncSession = Depends(get_db)):
    by_day = await get_day_options(db)
    options = [opt for day_options in by_day.values() for opt in day_options]
    options.sort(key=lambda o: (o.day, o.option_index))
    return [DailyRewardOptionOut.model_validate(o) for o in options]


@router.put("", response_model=list[DailyRewardOptionOut])
async def update_daily_reward_options(
    payload: DailyRewardOptionsUpdate, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    await _validate_options(db, payload.options)

    old_rows = (await db.execute(select(DailyRewardOption))).scalars().all()
    old_value = [DailyRewardOptionOut.model_validate(o).model_dump(mode="json") for o in old_rows]
    for row in old_rows:
        await db.delete(row)
    await db.flush()

    new_rows = [
        DailyRewardOption(
            day=opt.day, option_index=opt.option_index, coins=opt.coins,
            free_pack_slug=opt.free_pack_slug, grants_random_card=opt.grants_random_card,
        )
        for opt in payload.options
    ]
    db.add_all(new_rows)

    await log_action(
        db, admin.id, "update_daily_reward_options", "daily_reward_options", None,
        old_value={"options": old_value}, new_value=payload.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    new_rows.sort(key=lambda o: (o.day, o.option_index))
    return [DailyRewardOptionOut.model_validate(o) for o in new_rows]
