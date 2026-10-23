"""Admin: «Академия» catalog — talents (on/off, strength per level, order),
stages (name, rating band, talent level unlocked) and their gate tasks.
Experience / limits / prices / squad limits are GameConfig fields edited
through the existing PUT /admin/games/config; which players are path cards
is set on the player (PUT /admin/players/{id}, path_talent_code)."""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.database import get_db
from app.models.card import UserCard
from app.models.card_path import PathStage, PathStageTask, PathTalent
from app.models.enums import Position
from app.models.player import Player
from app.models.user import User
from app.services import path_service
from app.services.admin_log_service import log_action
from app.services.game_config_service import get_config
from app.services.path_talent_catalog import TALENTS, values_for

router = APIRouter(prefix="/admin/path", tags=["admin"], dependencies=[Depends(get_current_admin)])


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class TalentUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    sort_order: Optional[int] = None
    # {"1": {"bonus": 3}, "2": {...}} — only the catalog's own keys.
    level_values: Optional[dict[str, dict[str, int]]] = None


class StageUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    max_rating: Optional[int] = Field(default=None, ge=1, le=99)
    talent_level: Optional[int] = Field(default=None, ge=0, le=2)


class TaskIn(BaseModel):
    stage_index: int
    metric: str
    target: int = Field(ge=1, le=100000)
    positions: Optional[list[str]] = None
    sort_order: int = 0
    is_active: bool = True


async def _overview(db: AsyncSession) -> dict:
    config = await get_config(db)
    catalog = await path_service.load_catalog(db)
    all_tasks = (await db.execute(select(PathStageTask).order_by(PathStageTask.sort_order, PathStageTask.id))).scalars().all()
    players = (await db.execute(
        select(Player.id, Player.display_name, Player.position, Player.rating, Player.path_talent_code, Player.is_active)
        .where(Player.path_talent_code.is_not(None)).order_by(Player.display_name)
    )).all()
    owned = dict((await db.execute(
        select(UserCard.player_id, func.count(UserCard.id)).join(Player, Player.id == UserCard.player_id)
        .where(Player.path_talent_code.is_not(None)).group_by(UserCard.player_id)
    )).all())
    return {
        "title": config.path_title,
        "metrics": path_service.METRICS,
        "positions": [p.value for p in Position],
        "talents": [
            {
                "code": code, "name": t.name, "emoji": t.emoji, "kind": t.kind, "summary": t.summary,
                "level_text": list(t.level_text), "params": {k: list(v) for k, v in t.params.items()},
                "modes": t.modes, "positions": sorted(p.value for p in t.positions) if t.positions else None,
                "is_enabled": catalog.talents[code].is_enabled if code in catalog.talents else True,
                "sort_order": catalog.talents[code].sort_order if code in catalog.talents else 0,
                "level_values": {
                    str(lvl): values_for(code, lvl, catalog.talents[code].level_values if code in catalog.talents else None)
                    for lvl in (1, 2)
                },
                "players": sum(1 for p in players if p.path_talent_code == code),
            }
            for code, t in TALENTS.items()
        ],
        "stages": [
            {"index": s.stage_index, "name": s.name, "max_rating": s.max_rating, "talent_level": s.talent_level}
            for s in catalog.stages
        ],
        "tasks": [
            {"id": t.id, "stage_index": t.stage_index, "metric": t.metric, "target": t.target, "positions": t.positions,
             "sort_order": t.sort_order, "is_active": t.is_active}
            for t in all_tasks
        ],
        "players": [
            {"id": p.id, "display_name": p.display_name, "position": p.position.value, "rating": p.rating,
             "talent_code": p.path_talent_code, "is_active": p.is_active, "copies": owned.get(p.id, 0)}
            for p in players
        ],
    }


@router.get("")
async def overview(db: AsyncSession = Depends(get_db)):
    return await _overview(db)


@router.put("/talents/{code}")
async def update_talent(code: str, payload: TalentUpdate, request: Request, db: AsyncSession = Depends(get_db),
                        admin: User = Depends(get_current_admin)):
    if code not in TALENTS:
        raise NotFoundError("Талант не найден")
    await path_service.ensure_catalog(db)
    row = await db.get(PathTalent, code)
    old = {"is_enabled": row.is_enabled, "sort_order": row.sort_order, "level_values": row.level_values}
    if payload.is_enabled is not None:
        row.is_enabled = payload.is_enabled
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order
    if payload.level_values is not None:
        params = TALENTS[code].params
        clean: dict = {}
        for lvl in ("1", "2"):
            values = payload.level_values.get(lvl) or {}
            unknown = set(values) - set(params)
            if unknown:
                raise ConflictError(f"Неизвестные параметры: {', '.join(sorted(unknown))}")
            if any(int(v) < 0 or int(v) > 100 for v in values.values()):
                raise ConflictError("Значения должны быть от 0 до 100")
            clean[lvl] = {k: int(v) for k, v in values.items()}
        row.level_values = clean
    db.add(row)
    await log_action(db, admin.id, "update_path_talent", "path_talent", None, old_value=old,
                     new_value=payload.model_dump(exclude_unset=True), ip_address=_ip(request))
    await db.commit()
    return await _overview(db)


@router.put("/stages/{index}")
async def update_stage(index: int, payload: StageUpdate, request: Request, db: AsyncSession = Depends(get_db),
                       admin: User = Depends(get_current_admin)):
    await path_service.ensure_catalog(db)
    stage = await db.get(PathStage, index)
    if stage is None:
        raise NotFoundError("Этап не найден")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(stage, key, value)
    stages = sorted((await db.execute(select(PathStage))).scalars().all(), key=lambda s: s.stage_index)
    bounds = [s.max_rating for s in stages]
    if bounds != sorted(bounds) or len(set(bounds)) != len(bounds):
        raise ConflictError("Верхние границы этапов должны строго расти")
    db.add(stage)
    await log_action(db, admin.id, "update_path_stage", "path_stage", index, new_value=updates, ip_address=_ip(request))
    await db.commit()
    return await _overview(db)


def _validate_task(payload: TaskIn) -> None:
    if payload.metric not in path_service.METRICS:
        raise ConflictError("Неизвестная метрика")
    valid = {p.value for p in Position}
    if payload.positions and any(p not in valid for p in payload.positions):
        raise ConflictError("Неизвестная позиция")


@router.post("/tasks")
async def create_task(payload: TaskIn, request: Request, db: AsyncSession = Depends(get_db),
                      admin: User = Depends(get_current_admin)):
    _validate_task(payload)
    await path_service.ensure_catalog(db)
    if await db.get(PathStage, payload.stage_index) is None:
        raise NotFoundError("Этап не найден")
    task = PathStageTask(**{**payload.model_dump(), "positions": payload.positions or None})
    db.add(task)
    await db.flush()
    await log_action(db, admin.id, "create_path_task", "path_stage_task", task.id,
                     new_value=payload.model_dump(), ip_address=_ip(request))
    await db.commit()
    return await _overview(db)


@router.put("/tasks/{task_id}")
async def update_task(task_id: int, payload: TaskIn, request: Request, db: AsyncSession = Depends(get_db),
                      admin: User = Depends(get_current_admin)):
    _validate_task(payload)
    task = await db.get(PathStageTask, task_id)
    if task is None:
        raise NotFoundError("Задание не найдено")
    for key, value in payload.model_dump().items():
        setattr(task, key, value)
    task.positions = payload.positions or None
    db.add(task)
    await log_action(db, admin.id, "update_path_task", "path_stage_task", task_id,
                     new_value=payload.model_dump(), ip_address=_ip(request))
    await db.commit()
    return await _overview(db)


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, request: Request, db: AsyncSession = Depends(get_db),
                      admin: User = Depends(get_current_admin)):
    task = await db.get(PathStageTask, task_id)
    if task is None:
        raise NotFoundError("Задание не найдено")
    await db.delete(task)
    await log_action(db, admin.id, "delete_path_task", "path_stage_task", task_id, ip_address=_ip(request))
    await db.commit()
    return await _overview(db)
