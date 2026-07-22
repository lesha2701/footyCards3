from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.admin_action import AdminAction
from app.models.user import User
from app.schemas.admin import AdminActionLogOut

router = APIRouter(prefix="/admin/log", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=Page[AdminActionLogOut])
async def list_admin_actions(params: PageParams = Depends(), db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count(AdminAction.id)))).scalar_one()
    result = await db.execute(
        select(AdminAction, User.username)
        .join(User, User.id == AdminAction.admin_id)
        .order_by(AdminAction.created_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    rows = result.all()
    items = [
        AdminActionLogOut(**AdminActionLogOut.model_validate(action).model_dump() | {"admin_username": username})
        for action, username in rows
    ]
    return Page.build(items, total, params)
