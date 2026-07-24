from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.enums import Position, Rarity
from app.models.player import Player
from app.schemas.player import PlayerOut

router = APIRouter(prefix="/players", tags=["players"])


@router.get("", response_model=Page[PlayerOut])
async def list_players(
    params: PageParams = Depends(),
    rarity: Optional[Rarity] = None,
    country: Optional[str] = None,
    club: Optional[str] = None,
    position: Optional[Position] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    query = select(Player).where(Player.is_active.is_(True))
    if rarity:
        query = query.where(Player.rarity == rarity)
    if country:
        query = query.where(Player.country == country)
    if club:
        query = query.where(Player.club == club)
    if position:
        query = query.where(Player.position == position)
    if search:
        query = query.where(Player.display_name.ilike(f"%{search}%"))

    from sqlalchemy import func

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    query = query.order_by(Player.rating.desc()).offset(params.offset).limit(params.page_size)
    players: List[Player] = (await db.execute(query)).unique().scalars().all()
    return Page.build([PlayerOut.model_validate(p) for p in players], total, params)


@router.get("/{player_id}", response_model=PlayerOut)
async def get_player(player_id: int, db: AsyncSession = Depends(get_db), _user=Depends(get_current_user)):
    from app.core.exceptions import NotFoundError

    player = await db.get(Player, player_id)
    if not player or not player.is_active:
        raise NotFoundError("Player not found")
    return PlayerOut.model_validate(player)
