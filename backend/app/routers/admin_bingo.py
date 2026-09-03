from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_db
from app.models.user import User
from app.schemas.bingo import (
    BingoGoalDefinitionCreate,
    BingoGoalDefinitionOut,
    BingoGoalDefinitionUpdate,
    BingoStateOut,
    BingoStateUpdate,
    BingoStatsPreviewItem,
)
from app.services.admin_log_service import log_action
from app.services.bingo_service import (
    create_goal_definition,
    delete_goal_definition,
    get_state,
    get_stats_preview,
    list_goal_definitions,
    set_enabled,
    update_goal_definition,
)

router = APIRouter(prefix="/admin/bingo", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("/state", response_model=BingoStateOut)
async def get_bingo_state(db: AsyncSession = Depends(get_db)):
    return await get_state(db)


@router.put("/state", response_model=BingoStateOut)
async def update_bingo_state(
    payload: BingoStateUpdate, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    state = await set_enabled(db, payload.is_enabled)
    await log_action(
        db, admin.id, "update_bingo_state", "bingo_state", state.id,
        old_value=None, new_value={"is_enabled": payload.is_enabled},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return state


@router.get("/goals", response_model=list[BingoGoalDefinitionOut])
async def list_bingo_goals(db: AsyncSession = Depends(get_db)):
    return await list_goal_definitions(db)


@router.get("/stats-preview", response_model=list[BingoStatsPreviewItem])
async def get_bingo_stats_preview(db: AsyncSession = Depends(get_db)):
    return await get_stats_preview(db)


@router.post("/goals", response_model=BingoGoalDefinitionOut)
async def create_bingo_goal(
    payload: BingoGoalDefinitionCreate, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    definition = await create_goal_definition(db, payload.goal_type, payload.target_value, payload.is_active)
    await log_action(
        db, admin.id, "create_bingo_goal", "bingo_goal_definition", definition.id,
        old_value=None, new_value=payload.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return definition


@router.put("/goals/{goal_id}", response_model=BingoGoalDefinitionOut)
async def update_bingo_goal(
    goal_id: int, payload: BingoGoalDefinitionUpdate, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    updates = payload.model_dump(exclude_unset=True)
    definition = await update_goal_definition(db, goal_id, payload.target_value, payload.is_active)
    await log_action(
        db, admin.id, "update_bingo_goal", "bingo_goal_definition", goal_id,
        old_value=None, new_value=updates,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return definition


@router.delete("/goals/{goal_id}")
async def delete_bingo_goal(
    goal_id: int, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    await delete_goal_definition(db, goal_id)
    await log_action(
        db, admin.id, "delete_bingo_goal", "bingo_goal_definition", goal_id,
        old_value=None, new_value=None,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"ok": True}
