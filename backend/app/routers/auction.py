from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.enums import Position, Rarity
from app.models.user import User
from app.schemas.auction import (
    AuctionActionOut,
    AuctionBidIn,
    AuctionBuyNowIn,
    AuctionInfoOut,
    AuctionLotCreateIn,
    AuctionLotListOut,
    AuctionLotOut,
    AuctionPriceFloorOut,
    AuctionSort,
)
from app.services import auction_service

router = APIRouter(prefix="/auction", tags=["auction"])


@router.get("/info", response_model=AuctionInfoOut)
async def auction_info(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await auction_service.get_info(db, user)


@router.get("/lots", response_model=AuctionLotListOut)
async def list_lots(
    search: Optional[str] = Query(default=None, max_length=64),
    rarity: Optional[Rarity] = None,
    position: Optional[Position] = None,
    skill: Optional[str] = Query(default=None, max_length=32),
    min_stars: Optional[int] = Query(default=None, ge=0, le=10),
    min_price: Optional[int] = Query(default=None, ge=0),
    max_price: Optional[int] = Query(default=None, ge=0),
    sort: AuctionSort = "ending",
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await auction_service.list_lots(
        db, user, search=search, rarity=rarity, position=position.value if position else None, skill=skill,
        min_stars=min_stars, min_price=min_price, max_price=max_price, sort=sort, limit=limit, offset=offset,
    )


@router.get("/price-floor/{user_card_id}", response_model=AuctionPriceFloorOut)
async def price_floor(user_card_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await auction_service.price_floor_for(db, user, user_card_id)


@router.get("/my-lots", response_model=list[AuctionLotOut])
async def my_lots(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await auction_service.my_lots(db, user)


@router.get("/my-bids", response_model=list[AuctionLotOut])
async def my_bids(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await auction_service.my_bids(db, user)


@router.get("/lots/{lot_id}", response_model=AuctionLotOut)
async def get_lot(lot_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await auction_service.get_lot(db, user, lot_id)


@router.post("/lots", response_model=AuctionLotOut)
async def create_lot(payload: AuctionLotCreateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"auction_create:{user.id}", max_calls=10, window_seconds=60)
    return await auction_service.create_lot(db, user, payload)


@router.post("/lots/{lot_id}/bid", response_model=AuctionActionOut)
async def place_bid(
    lot_id: int, payload: AuctionBidIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await check_rate_limit(f"auction_bid:{user.id}", max_calls=30, window_seconds=60)
    return await auction_service.place_bid(db, user, lot_id, payload)


@router.post("/lots/{lot_id}/buy-now", response_model=AuctionActionOut)
async def buy_now(
    lot_id: int, payload: AuctionBuyNowIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await check_rate_limit(f"auction_buy:{user.id}", max_calls=20, window_seconds=60)
    return await auction_service.buy_now(db, user, lot_id, payload)


@router.post("/lots/{lot_id}/cancel", response_model=AuctionLotOut)
async def cancel_lot(lot_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await auction_service.cancel_lot(db, user, lot_id)
