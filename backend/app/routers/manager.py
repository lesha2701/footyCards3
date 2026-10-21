from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.manager import (
    ManagerClubUpdateIn,
    ManagerFoundIn,
    ManagerLookIn,
    ManagerMarketIn,
    ManagerNpcIn,
    ManagerOfferIn,
    ManagerRespondIn,
    ManagerStadiumNameIn,
)
from app.services import manager_service, manager_shop

router = APIRouter(prefix="/manager", tags=["manager"])


@router.get("")
async def get_manager(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """My club (budget, squad, contracts, footballers, requests), my contract
    as a player, offers to me, the season phase and the league (the season
    start and due rounds run first)."""
    return await manager_service.get_view(db, user)


@router.get("/market")
async def get_market(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Users' «Мои игроки»: free agents, friends and players of other clubs."""
    return await manager_service.market(db, user)


@router.get("/npc")
async def get_npc_catalog(
    line: Optional[str] = Query(default=None, max_length=3),
    q: Optional[str] = Query(default=None, max_length=40),
    offset: int = Query(default=0, ge=0, le=5000),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    """Footballers of the game catalog with value, wage and loan price."""
    return await manager_service.npc_catalog(db, user, line, q, offset)


@router.post("/club")
async def found_club(payload: ManagerFoundIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"manager_club:{user.id}", max_calls=5, window_seconds=60)
    return await manager_service.found_club(db, user, payload.name)


@router.patch("/club")
async def update_club(payload: ManagerClubUpdateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"manager_club:{user.id}", max_calls=20, window_seconds=60)
    return await manager_service.update_club(
        db, user, payload.name, payload.formation, payload.style, payload.academy_card_id, payload.clear_academy,
    )


@router.post("/offers")
async def make_offer(payload: ManagerOfferIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Sign a free agent, or ask another club for a transfer / a loan."""
    await check_rate_limit(f"manager_offer:{user.id}", max_calls=20, window_seconds=60)
    return await manager_service.make_offer(db, user, payload.user_id, payload.wage, payload.seasons, payload.fee, payload.kind)


@router.post("/offers/{contract_id}/cancel")
async def cancel_offer(contract_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await manager_service.cancel_offer(db, user, contract_id)


@router.post("/offers/{contract_id}/respond")
async def respond_offer(
    contract_id: int, payload: ManagerRespondIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    """The player or the selling club's owner answers."""
    await check_rate_limit(f"manager_offer:{user.id}", max_calls=20, window_seconds=60)
    return await manager_service.respond_offer(db, user, contract_id, payload.accept)


@router.post("/contracts/{contract_id}/end")
async def end_contract(contract_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """The player leaves or the club releases him (not during a season)."""
    return await manager_service.end_contract(db, user, contract_id)


@router.post("/market")
async def set_market(payload: ManagerMarketIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """List / unlist my «Мой игрок» as a free agent."""
    return await manager_service.set_market(db, user, payload.open)


@router.post("/npc")
async def sign_npc(payload: ManagerNpcIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Buy a catalog footballer (1-3 seasons) or loan him for a season."""
    await check_rate_limit(f"manager_npc:{user.id}", max_calls=30, window_seconds=60)
    return await manager_service.sign_npc(db, user, payload.player_id, payload.kind, payload.seasons)


@router.post("/npc/{npc_id}/release")
async def release_npc(npc_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Sell a bought footballer back to the system, or end a loan."""
    return await manager_service.release_npc(db, user, npc_id)


# --- style, merchandise, Pro (manager_shop) ----------------------------------------------------

@router.post("/shop/{code}")
async def buy_cosmetic(code: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """A style item for coins (Stars go through /my-player/stars-invoice, purchase "manager")."""
    await check_rate_limit(f"manager_shop:{user.id}", max_calls=20, window_seconds=60)
    return await manager_shop.buy_cosmetic(db, user, code)


@router.patch("/look")
async def set_look(payload: ManagerLookIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"manager_shop:{user.id}", max_calls=40, window_seconds=60)
    return await manager_shop.set_look(db, user, payload.model_dump(exclude_none=True))


@router.post("/stadium-name")
async def set_stadium_name(payload: ManagerStadiumNameIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await manager_shop.set_stadium_name(db, user, payload.name)


@router.get("/clubs/{club_id}")
async def get_club_card(club_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Any club's public card: style, division, fans, merchandise."""
    return await manager_shop.club_card(db, user, club_id)


@router.post("/clubs/{club_id}/merch/{code}")
async def buy_merch(club_id: int, code: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """A fan buys merchandise of another club: coins burned, euros to the club."""
    await check_rate_limit(f"manager_merch:{user.id}", max_calls=20, window_seconds=60)
    return await manager_shop.buy_merch(db, user, club_id, code)


@router.get("/popular")
async def get_popular(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Clubs with the most fans."""
    return await manager_shop.popular(db)


@router.get("/scout")
async def get_scout(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """«Менеджер Pro»: the market's biggest value risers."""
    return await manager_shop.scout(db, user)
