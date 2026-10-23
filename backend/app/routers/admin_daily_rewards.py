from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_db
from app.models.user import User
from app.schemas.monetization import CalendarTemplateDayOut, CalendarTemplateIn
from app.services import daily_reward_service
from app.services.admin_log_service import log_action

router = APIRouter(prefix="/admin/login-calendar", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=list[CalendarTemplateDayOut])
async def read_template(db: AsyncSession = Depends(get_db)):
    return await daily_reward_service.admin_template(db)


@router.put("", response_model=list[CalendarTemplateDayOut])
async def update_template(
    payload: CalendarTemplateIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    old_value = [d.model_dump(mode="json") for d in await daily_reward_service.admin_template(db)]
    result = await daily_reward_service.admin_update_template(db, payload)
    await log_action(
        db, admin.id, "update_login_calendar", "login_calendar_days", None,
        old_value={"days": old_value}, new_value=payload.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return result
