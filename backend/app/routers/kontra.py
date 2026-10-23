from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.kontra import (
    KontraActRequest,
    KontraArenaOut,
    KontraArenaStartRequest,
    KontraAutoRequest,
    KontraBattleOut,
    KontraBossOut,
    KontraGearEquipRequest,
    KontraGearListOut,
    KontraHubOut,
    KontraSquadOut,
    KontraSquadSetRequest,
    KontraStartRequest,
)
from app.schemas.stars import StarsInvoiceCreateOut
from app.services import kontra_service, shop_product_service

router = APIRouter(prefix="/kontra", tags=["kontra"])


@router.get("/hub", response_model=KontraHubOut)
async def get_hub(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await kontra_service.get_hub(db, user)


@router.get("/squad", response_model=KontraSquadOut)
async def get_squad(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await kontra_service.get_squad(db, user)


@router.put("/squad", response_model=KontraSquadOut)
async def set_squad(payload: KontraSquadSetRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await kontra_service.set_squad(db, user, payload.cards, payload.leader)


@router.post("/squad/auto", response_model=KontraSquadOut)
async def auto_squad(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await kontra_service.auto_squad(db, user)


@router.get("/arena", response_model=KontraArenaOut)
async def get_arena(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await kontra_service.get_arena(db, user)


@router.post("/arena/refresh", response_model=KontraArenaOut)
async def refresh_arena(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"kontra_refresh:{user.id}", max_calls=20, window_seconds=60)
    return await kontra_service.get_arena(db, user, refresh=True)


@router.post("/arena/start", response_model=KontraBattleOut)
async def start_arena(payload: KontraArenaStartRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"kontra_start:{user.id}", max_calls=20, window_seconds=60)
    return await kontra_service.start_arena(db, user, payload.offer, payload.manual)


@router.get("/boss", response_model=KontraBossOut)
async def get_boss(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await kontra_service.get_boss(db, user)


@router.post("/boss/start", response_model=KontraBattleOut)
async def start_boss(
    payload: KontraStartRequest | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await check_rate_limit(f"kontra_start:{user.id}", max_calls=20, window_seconds=60)
    return await kontra_service.start_boss(db, user, (payload or KontraStartRequest()).manual)


@router.get("/battles/{battle_id}", response_model=KontraBattleOut)
async def get_battle(battle_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await kontra_service.get_battle(db, user, battle_id)


@router.post("/battles/{battle_id}/act", response_model=KontraBattleOut)
async def act(battle_id: int, payload: KontraActRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"kontra_act:{user.id}", max_calls=180, window_seconds=60)
    return await kontra_service.act(db, user, battle_id, payload.version, payload.unit_id, payload.ability, payload.target_id)


@router.post("/battles/{battle_id}/auto", response_model=KontraBattleOut)
async def autoplay(battle_id: int, payload: KontraAutoRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await kontra_service.autoplay(db, user, battle_id, payload.version)


@router.post("/battles/{battle_id}/forfeit", response_model=KontraBattleOut)
async def forfeit(battle_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await kontra_service.forfeit(db, user, battle_id)


@router.get("/gear", response_model=KontraGearListOut)
async def list_gear(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await kontra_service.list_gear(db, user)


@router.post("/gear/{gear_id}/equip", response_model=KontraGearListOut)
async def equip_gear(
    gear_id: int, payload: KontraGearEquipRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await kontra_service.equip_gear(db, user, gear_id, payload.card_id)


@router.post("/gear/chest", response_model=KontraGearListOut)
async def buy_chest(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"kontra_chest:{user.id}", max_calls=30, window_seconds=60)
    listing, _ = await kontra_service.buy_chest(db, user)
    return listing


@router.post("/gear/chest/stars-invoice", response_model=StarsInvoiceCreateOut)
async def chest_invoice(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await shop_product_service.create_invoice(db, user, *await kontra_service.stars_order(db, user))
