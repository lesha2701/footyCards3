from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.equipment import EquipmentBuyIn, EquipmentEquipIn, EquipmentUnequipIn
from app.schemas.stars import StarsInvoiceCreateOut
from app.services import equipment_service, shop_product_service

router = APIRouter(prefix="/equipment", tags=["equipment"])


@router.get("/shop")
async def equipment_shop(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await equipment_service.shop(db, user)


@router.get("/inventory")
async def equipment_inventory(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await equipment_service.inventory(db, user)


@router.get("/cards/{card_id}")
async def card_equipment(card_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await equipment_service.card_equipment(db, user, card_id)


@router.post("/items/{item_id}/buy")
async def buy_item(
    item_id: int, payload: EquipmentBuyIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await equipment_service.buy_with_coins(db, user, item_id, payload.idempotency_key)


@router.post("/items/{item_id}/stars-invoice", response_model=StarsInvoiceCreateOut)
async def item_invoice(item_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await shop_product_service.create_invoice(db, user, *await equipment_service.stars_order(db, user, item_id))


@router.post("/equip")
async def equip(payload: EquipmentEquipIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await equipment_service.equip(db, user, payload.copy_id, payload.user_card_id)


@router.post("/unequip")
async def unequip(payload: EquipmentUnequipIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await equipment_service.unequip(db, user, payload.copy_id)
