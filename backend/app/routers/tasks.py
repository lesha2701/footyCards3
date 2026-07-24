from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.task import TaskClaimOut, TaskListOut
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=TaskListOut)
async def get_my_tasks(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await task_service.list_my_tasks(db, user)


@router.post("/{user_task_id}/claim", response_model=TaskClaimOut)
async def claim_task(user_task_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await task_service.claim_task_reward(db, user, user_task_id)
