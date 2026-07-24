from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.enums import NotificationType, TaskCategory
from app.models.task import TaskDefinition
from app.models.user import User
from app.schemas.task import TaskDefinitionCreate, TaskDefinitionOut, TaskDefinitionUpdate
from app.services import notification_service
from app.services.admin_log_service import log_action

router = APIRouter(prefix="/admin/tasks", tags=["admin"], dependencies=[Depends(get_current_admin)])


async def _get_task_or_404(db: AsyncSession, task_id: int) -> TaskDefinition:
    task = await db.get(TaskDefinition, task_id)
    if not task:
        raise NotFoundError("Task not found")
    return task


@router.get("", response_model=list[TaskDefinitionOut])
async def list_all_tasks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TaskDefinition).order_by(TaskDefinition.sort_order))
    return [TaskDefinitionOut.model_validate(t) for t in result.scalars().all()]


@router.post("", response_model=TaskDefinitionOut)
async def create_task(payload: TaskDefinitionCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    task = TaskDefinition(**payload.model_dump())
    db.add(task)
    await db.flush()
    await log_action(db, admin.id, "create_task", "task_definition", task.id, new_value=payload.model_dump(mode="json"), ip_address=request.client.host if request.client else None)

    if task.category == TaskCategory.premium:
        result = await db.execute(select(User.id).where(User.is_banned.is_(False)))
        for (user_id,) in result.all():
            await notification_service.notify(
                db, user_id, NotificationType.premium_task_available,
                "⭐ Новое премиум-задание!",
                f"Доступно новое задание: «{task.name}». Загляни в приложение!",
                "task_definition", task.id,
            )

    await db.commit()
    return TaskDefinitionOut.model_validate(task)


@router.put("/{task_id}", response_model=TaskDefinitionOut)
async def update_task(task_id: int, payload: TaskDefinitionUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    task = await _get_task_or_404(db, task_id)
    old_value = TaskDefinitionOut.model_validate(task).model_dump(mode="json")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(task, key, value)

    db.add(task)
    await log_action(
        db, admin.id, "update_task", "task_definition", task_id, old_value=old_value,
        new_value=payload.model_dump(mode="json", exclude_unset=True),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(task)
    return TaskDefinitionOut.model_validate(task)


@router.post("/{task_id}/toggle-active", response_model=TaskDefinitionOut)
async def toggle_task_active(task_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    task = await _get_task_or_404(db, task_id)
    task.is_active = not task.is_active
    db.add(task)
    await log_action(db, admin.id, "toggle_task_active", "task_definition", task_id, new_value={"is_active": task.is_active}, ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(task)
    return TaskDefinitionOut.model_validate(task)
