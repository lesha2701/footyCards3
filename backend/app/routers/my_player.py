from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.my_player import (
    MyPlayerCosmeticBuyIn,
    MyPlayerCosmeticEquipIn,
    MyPlayerCreateIn,
    MyPlayerLeaderboardOut,
    MyPlayerPublicOut,
    MyPlayerSkillIn,
    MyPlayerStarsInvoiceIn,
    MyPlayerStarsInvoiceOut,
    MyPlayerTrainIn,
    MyPlayerTrainingFinishIn,
    MyPlayerTrainingStartOut,
    MyPlayerUpdateIn,
    MyPlayerViewOut,
)
from app.schemas.stars import StarsInvoiceStatusOut
from app.services import my_player_service, stars_payment_service

router = APIRouter(prefix="/my-player", tags=["my-player"])


@router.get("", response_model=MyPlayerViewOut)
async def get_my_player(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await my_player_service.get_view(db, user)


@router.post("", response_model=MyPlayerViewOut)
async def create_my_player(payload: MyPlayerCreateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"my_player_create:{user.id}", max_calls=10, window_seconds=60)
    return await my_player_service.create(db, user, payload.name, payload.number, payload.position, payload.appearance)


@router.patch("", response_model=MyPlayerViewOut)
async def update_my_player(payload: MyPlayerUpdateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"my_player_update:{user.id}", max_calls=20, window_seconds=60)
    return await my_player_service.update(db, user, payload.name, payload.number, payload.position, payload.appearance)


@router.post("/train", response_model=MyPlayerViewOut)
async def train_my_player(payload: MyPlayerTrainIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"my_player_train:{user.id}", max_calls=60, window_seconds=60)
    return await my_player_service.train(db, user, payload.attr, payload.points)


@router.get("/users/{user_id}", response_model=MyPlayerPublicOut)
async def get_public_my_player(user_id: int, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await my_player_service.public_view(db, user_id)


@router.put("/skill", response_model=MyPlayerViewOut)
async def set_my_player_skill(payload: MyPlayerSkillIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"my_player_skill:{user.id}", max_calls=20, window_seconds=60)
    return await my_player_service.set_skill(db, user, payload.code)


@router.post("/training/start", response_model=MyPlayerTrainingStartOut)
async def start_training(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"my_player_training:{user.id}", max_calls=10, window_seconds=60)
    return await my_player_service.training_start(db, user)


@router.post("/training/finish", response_model=MyPlayerViewOut)
async def finish_training(
    payload: MyPlayerTrainingFinishIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await check_rate_limit(f"my_player_training:{user.id}", max_calls=10, window_seconds=60)
    return await my_player_service.training_finish(db, user, payload.hits)


@router.post("/cosmetics/buy", response_model=MyPlayerViewOut)
async def buy_cosmetic(payload: MyPlayerCosmeticBuyIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"my_player_cosmetic:{user.id}", max_calls=20, window_seconds=60)
    return await my_player_service.buy_cosmetic(db, user, payload.code)


@router.put("/cosmetics/equip", response_model=MyPlayerViewOut)
async def equip_cosmetic(payload: MyPlayerCosmeticEquipIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"my_player_cosmetic:{user.id}", max_calls=30, window_seconds=60)
    return await my_player_service.equip_cosmetic(db, user, payload.kind, payload.code)


@router.get("/leaderboard", response_model=MyPlayerLeaderboardOut)
async def get_leaderboard(
    scope: Literal["all", "friends"] = Query("all"),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await my_player_service.leaderboard(db, user, scope)


@router.post("/skill/upgrade", response_model=MyPlayerViewOut)
async def upgrade_my_player_skill(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"my_player_skill:{user.id}", max_calls=20, window_seconds=60)
    return await my_player_service.upgrade_skill(db, user)


@router.post("/extra-training/buy", response_model=MyPlayerViewOut)
async def buy_extra_training(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"my_player_extra:{user.id}", max_calls=10, window_seconds=60)
    return await my_player_service.buy_extra_training(db, user)


@router.post("/stars-invoice", response_model=MyPlayerStarsInvoiceOut)
async def create_stars_invoice(
    payload: MyPlayerStarsInvoiceIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await check_rate_limit(f"my_player_stars:{user.id}", max_calls=10, window_seconds=60)
    return await my_player_service.create_stars_invoice(db, user, payload.purchase, payload.item_id)


@router.get("/stars-invoices/{payload_token}", response_model=StarsInvoiceStatusOut)
async def get_stars_invoice_status(payload_token: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stars_payment_service.get_invoice_status(db, user, payload_token)
