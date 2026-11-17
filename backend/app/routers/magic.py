from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.magic import (
    MagicActRequest,
    MagicArmyOut,
    MagicArmySetRequest,
    MagicBuyRequest,
    MagicCastRequest,
    MagicChooseRequest,
    MagicExtraRunOut,
    MagicHealOut,
    MagicShopBuyOut,
    MagicShopBuyRequest,
    MagicShopOut,
    MagicPackOpenOut,
    MagicHubOut,
    MagicMoveRequest,
    MagicRetryRequest,
    MagicRunOut,
    MagicStartRequest,
    MagicVersionRequest,
)
from app.schemas.stars import StarsInvoiceCreateOut
from app.services import magic_service, shop_product_service

router = APIRouter(prefix="/magic", tags=["magic"])


@router.get("/hub", response_model=MagicHubOut)
async def get_hub(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await magic_service.get_hub(db, user)


HeroClassQuery = Optional[Literal["knight", "mage", "ranger"]]


@router.get("/army", response_model=MagicArmyOut)
async def get_army(hero_class: HeroClassQuery = None, db: AsyncSession = Depends(get_db),
                   user: User = Depends(get_current_user)):
    return await magic_service.get_army(db, user, hero_class)


@router.put("/army", response_model=MagicArmyOut)
async def set_army(payload: MagicArmySetRequest, hero_class: HeroClassQuery = None, db: AsyncSession = Depends(get_db),
                   user: User = Depends(get_current_user)):
    return await magic_service.set_army(db, user, payload.stacks, hero_class)


@router.post("/army/auto", response_model=MagicArmyOut)
async def auto_army(hero_class: HeroClassQuery = None, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    return await magic_service.auto_army(db, user, hero_class)


@router.post("/runs", response_model=MagicRunOut)
async def start_run(payload: MagicStartRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_start:{user.id}", max_calls=20, window_seconds=60)
    return await magic_service.start_run(db, user, payload.faction, payload.difficulty, payload.mode, payload.challenge,
                                         payload.hero_class)


@router.get("/runs/{run_id}", response_model=MagicRunOut)
async def get_run(run_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await magic_service.get_run(db, user, run_id)


@router.post("/runs/{run_id}/move", response_model=MagicRunOut)
async def move(run_id: int, payload: MagicMoveRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_act:{user.id}", max_calls=240, window_seconds=60)
    return await magic_service.move(db, user, run_id, payload.version, payload.x, payload.y)


@router.post("/runs/{run_id}/end-day", response_model=MagicRunOut)
async def end_day(run_id: int, payload: MagicVersionRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_act:{user.id}", max_calls=240, window_seconds=60)
    return await magic_service.end_day(db, user, run_id, payload.version)


@router.post("/runs/{run_id}/battle/act", response_model=MagicRunOut)
async def battle_act(run_id: int, payload: MagicActRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_act:{user.id}", max_calls=240, window_seconds=60)
    return await magic_service.battle_act(db, user, run_id, payload.version, payload.unit, payload.action,
                                          payload.target, payload.x, payload.y)


@router.post("/runs/{run_id}/battle/cast", response_model=MagicRunOut)
async def battle_cast(run_id: int, payload: MagicCastRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_act:{user.id}", max_calls=240, window_seconds=60)
    return await magic_service.battle_cast(db, user, run_id, payload.version, payload.spell, payload.target)


@router.post("/runs/{run_id}/battle/auto", response_model=MagicRunOut)
async def battle_auto(run_id: int, payload: MagicVersionRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await magic_service.battle_auto(db, user, run_id, payload.version)


@router.post("/runs/{run_id}/battle/leave", response_model=MagicRunOut)
async def battle_leave(run_id: int, payload: MagicVersionRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await magic_service.battle_leave(db, user, run_id, payload.version)


@router.post("/runs/{run_id}/forfeit", response_model=MagicRunOut)
async def forfeit(run_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await magic_service.forfeit(db, user, run_id)


@router.post("/runs/{run_id}/choose", response_model=MagicRunOut)
async def choose(run_id: int, payload: MagicChooseRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_act:{user.id}", max_calls=240, window_seconds=60)
    return await magic_service.choose(db, user, run_id, payload.version, payload.option)


@router.post("/runs/{run_id}/market", response_model=MagicRunOut)
async def market_buy(run_id: int, payload: MagicBuyRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_act:{user.id}", max_calls=240, window_seconds=60)
    return await magic_service.buy(db, user, run_id, payload.version, payload.object_id, payload.index)


@router.post("/runs/{run_id}/accept", response_model=MagicRunOut)
async def accept_defeat(run_id: int, payload: MagicVersionRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await magic_service.accept_defeat(db, user, run_id, payload.version)


@router.post("/runs/{run_id}/retry", response_model=MagicRunOut)
async def retry_final(run_id: int, payload: MagicRetryRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_buy:{user.id}", max_calls=10, window_seconds=60)
    return await magic_service.retry_final(db, user, run_id, payload.version, payload.pay)


@router.post("/runs/{run_id}/retry/stars-invoice", response_model=StarsInvoiceCreateOut)
async def retry_stars(run_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_buy:{user.id}", max_calls=10, window_seconds=60)
    return await shop_product_service.create_invoice(db, user, *await magic_service.retry_stars_order(db, user, run_id))


@router.post("/creature-pack", response_model=MagicPackOpenOut)
async def creature_pack_coins(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_buy:{user.id}", max_calls=10, window_seconds=60)
    return await magic_service.buy_creature_pack(db, user)


@router.post("/creature-pack/stars-invoice", response_model=StarsInvoiceCreateOut)
async def creature_pack_stars(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_buy:{user.id}", max_calls=10, window_seconds=60)
    return await shop_product_service.create_invoice(db, user, *await magic_service.creature_pack_stars_order(db, user))


class _Count(BaseModel):
    count: int = Field(default=1, ge=1, le=50)


class _Code(BaseModel):
    code: str = Field(min_length=1, max_length=20)


class _Player(BaseModel):
    player_id: int


@router.post("/captains/{player_id}/feed", response_model=MagicArmyOut)
async def captain_feed(player_id: int, body: _Count, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_buy:{user.id}", max_calls=20, window_seconds=60)
    return await magic_service.feed_captain(db, user, player_id, body.count)


@router.post("/captains/{player_id}/trait", response_model=MagicArmyOut)
async def captain_trait(player_id: int, body: _Code, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    return await magic_service.set_captain_trait(db, user, player_id, body.code)


@router.put("/guard", response_model=MagicArmyOut)
async def guard_set(body: _Player, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await magic_service.set_guard(db, user, body.player_id)


@router.post("/guard/refill", response_model=MagicArmyOut)
async def guard_refill(body: _Player, count: int = 1, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_buy:{user.id}", max_calls=20, window_seconds=60)
    return await magic_service.refill_guard(db, user, body.player_id, max(1, min(50, count)))


@router.post("/guard/trait", response_model=MagicArmyOut)
async def guard_trait(body: _Code, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await magic_service.set_guard_trait(db, user, body.code)


@router.post("/revive", response_model=MagicHealOut)
async def revive(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await magic_service.revive_free(db, user)


@router.get("/shop", response_model=MagicShopOut)
async def essence_shop(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await magic_service.get_shop(db, user)


@router.post("/shop/buy", response_model=MagicShopBuyOut)
async def essence_shop_buy(body: MagicShopBuyRequest, db: AsyncSession = Depends(get_db),
                           user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_buy:{user.id}", max_calls=10, window_seconds=60)
    return await magic_service.buy_in_shop(db, user, body.code)


@router.post("/heal", response_model=MagicHealOut)
async def heal_essence(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_buy:{user.id}", max_calls=10, window_seconds=60)
    return await magic_service.heal_for_essence(db, user)


@router.post("/heal/stars-invoice", response_model=StarsInvoiceCreateOut)
async def heal_stars(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_buy:{user.id}", max_calls=10, window_seconds=60)
    return await shop_product_service.create_invoice(db, user, *await magic_service.heal_stars_order(db, user))


@router.post("/extra-run", response_model=MagicExtraRunOut)
async def extra_run_coins(mode: str = Query("quick", pattern="^(quick|hardcore|adventure)$"),
                          db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_buy:{user.id}", max_calls=10, window_seconds=60)
    return await magic_service.buy_extra_run(db, user, mode)


@router.post("/extra-run/stars-invoice", response_model=StarsInvoiceCreateOut)
async def extra_run_stars(mode: str = Query("quick", pattern="^(quick|hardcore|adventure)$"),
                          db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magic_buy:{user.id}", max_calls=10, window_seconds=60)
    return await shop_product_service.create_invoice(db, user, *await magic_service.extra_run_stars_order(db, user, mode))
