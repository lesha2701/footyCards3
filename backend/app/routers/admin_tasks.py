from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.task import TaskDefinition, UserTask
from app.models.user import User
from app.schemas.broadcast import PremiumTaskBroadcastCreate, PremiumTaskBroadcastOut
from app.schemas.task import TaskDefinitionCreate, TaskDefinitionOut, TaskDefinitionStatsOut, TaskDefinitionUpdate
from app.services.admin_log_service import log_action
from app.services.broadcast_service import send_premium_task_broadcast

router = APIRouter(prefix="/admin/tasks", tags=["admin"], dependencies=[Depends(get_current_admin)])


async def _get_task_or_404(db: AsyncSession, task_id: int) -> TaskDefinition:
    task = await db.get(TaskDefinition, task_id)
    if not task:
        raise NotFoundError("Task not found")
    return task


@router.get("", response_model=list[TaskDefinitionStatsOut])
async def list_all_tasks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TaskDefinition).order_by(TaskDefinition.sort_order))
    tasks = result.scalars().all()

    stats_result = await db.execute(
        select(
            UserTask.task_definition_id,
            func.count(UserTask.id).filter(UserTask.completed_at.is_not(None)),
            func.count(UserTask.id).filter(UserTask.reward_claimed.is_(True)),
        ).group_by(UserTask.task_definition_id)
    )
    stats = {task_definition_id: (completed, claimed) for task_definition_id, completed, claimed in stats_result.all()}

    return [
        TaskDefinitionStatsOut(
            **TaskDefinitionOut.model_validate(t).model_dump(),
            completed_count=stats.get(t.id, (0, 0))[0],
            claimed_count=stats.get(t.id, (0, 0))[1],
        )
        for t in tasks
    ]


@router.post("", response_model=TaskDefinitionOut)
async def create_task(payload: TaskDefinitionCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    task = TaskDefinition(**payload.model_dump())
    db.add(task)
    await db.flush()
    await log_action(db, admin.id, "create_task", "task_definition", task.id, new_value=payload.model_dump(mode="json"), ip_address=request.client.host if request.client else None)

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


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    task = await _get_task_or_404(db, task_id)

    await log_action(db, admin.id, "delete_task", "task_definition", task_id, old_value=TaskDefinitionOut.model_validate(task).model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    await db.delete(task)
    await db.commit()


@router.post("/broadcast-premium", response_model=PremiumTaskBroadcastOut)
async def broadcast_premium_tasks(
    payload: PremiumTaskBroadcastCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    recipients = await send_premium_task_broadcast(db, payload.task_count, payload.message)
    await log_action(
        db, admin.id, "broadcast_premium_tasks", "task_definition", 0,
        new_value={"task_count": payload.task_count, "message": payload.message, "recipients": recipients},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return PremiumTaskBroadcastOut(recipients=recipients)


@router.post("/{task_id}/toggle-active", response_model=TaskDefinitionOut)
async def toggle_task_active(task_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    task = await _get_task_or_404(db, task_id)
    task.is_active = not task.is_active
    db.add(task)
    await log_action(db, admin.id, "toggle_task_active", "task_definition", task_id, new_value={"is_active": task.is_active}, ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(task)
    return TaskDefinitionOut.model_validate(task)
