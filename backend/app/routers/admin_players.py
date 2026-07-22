from typing import Optional

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.card import UserCard
from app.models.player import Player
from app.models.user import User
from app.schemas.admin import CsvImportResultOut
from app.schemas.player import PlayerCreate, PlayerOut, PlayerUpdate
from app.services.admin_log_service import log_action
from app.services.csv_service import export_players_csv, import_players_csv
from app.services.image_service import delete_player_image, save_player_image

router = APIRouter(prefix="/admin/players", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=Page[PlayerOut])
async def list_all_players(
    search: Optional[str] = None,
    include_inactive: bool = True,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    query = select(Player)
    count_query = select(func.count(Player.id))
    if not include_inactive:
        query = query.where(Player.is_active.is_(True))
        count_query = count_query.where(Player.is_active.is_(True))
    if search:
        query = query.where(Player.display_name.ilike(f"%{search}%"))
        count_query = count_query.where(Player.display_name.ilike(f"%{search}%"))

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(Player.id.desc()).offset(params.offset).limit(params.page_size)
    players = (await db.execute(query)).scalars().all()
    return Page.build([PlayerOut.model_validate(p) for p in players], total, params)


@router.get("/export-csv", response_class=PlainTextResponse)
async def export_csv(db: AsyncSession = Depends(get_db)):
    return await export_players_csv(db)


@router.post("/import-csv", response_model=CsvImportResultOut)
async def import_csv(
    request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)
):
    content = (await file.read()).decode("utf-8-sig")
    result = await import_players_csv(db, content)
    await log_action(
        db, admin.id, "import_players_csv", "player", None, new_value=result,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return result


@router.post("", response_model=PlayerOut)
async def create_player(payload: PlayerCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    player = Player(**payload.model_dump())
    db.add(player)
    await db.flush()
    await log_action(db, admin.id, "create_player", "player", player.id, new_value=payload.model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(player)
    return player


async def _get_player_or_404(db: AsyncSession, player_id: int) -> Player:
    player = await db.get(Player, player_id)
    if not player:
        raise NotFoundError("Player not found")
    return player


@router.put("/{player_id}", response_model=PlayerOut)
async def update_player(player_id: int, payload: PlayerUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    player = await _get_player_or_404(db, player_id)
    old_value = PlayerOut.model_validate(player).model_dump(mode="json")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(player, key, value)
    db.add(player)
    await log_action(db, admin.id, "update_player", "player", player_id, old_value=old_value, new_value=updates, ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(player)
    return player


@router.post("/{player_id}/toggle-active", response_model=PlayerOut)
async def toggle_active(player_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    player = await _get_player_or_404(db, player_id)
    player.is_active = not player.is_active
    db.add(player)
    await log_action(db, admin.id, "toggle_player_active", "player", player_id, new_value={"is_active": player.is_active}, ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(player)
    return player


@router.delete("/{player_id}")
async def delete_player(player_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    player = await _get_player_or_404(db, player_id)
    card_count = (await db.execute(select(func.count(UserCard.id)).where(UserCard.player_id == player_id))).scalar_one()
    if card_count > 0:
        raise ConflictError(
            f"Cannot delete: {card_count} card instance(s) reference this player. Deactivate it instead.",
            details={"card_count": card_count},
        )
    delete_player_image(player.image_path)
    await log_action(db, admin.id, "delete_player", "player", player_id, old_value={"display_name": player.display_name}, ip_address=request.client.host if request.client else None)
    await db.delete(player)
    await db.commit()
    return {"status": "ok"}


@router.post("/{player_id}/image", response_model=PlayerOut)
async def upload_image(player_id: int, request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    player = await _get_player_or_404(db, player_id)
    old_path = player.image_path
    new_path = await save_player_image(file, player.rarity, player.display_name)
    player.image_path = new_path
    db.add(player)
    if old_path:
        delete_player_image(old_path)
    await log_action(db, admin.id, "upload_player_image", "player", player_id, old_value={"image_path": old_path}, new_value={"image_path": new_path}, ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(player)
    return player


@router.delete("/{player_id}/image", response_model=PlayerOut)
async def remove_image(player_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    player = await _get_player_or_404(db, player_id)
    old_path = player.image_path
    delete_player_image(old_path)
    player.image_path = None
    db.add(player)
    await log_action(db, admin.id, "delete_player_image", "player", player_id, old_value={"image_path": old_path}, ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(player)
    return player
