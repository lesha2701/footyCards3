from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin, get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.card_offer import (
    CardOfferAdminIn,
    CardOfferAdminOut,
    CardOfferAnnounceOut,
    CardOfferOut,
    CardOffersSeenIn,
)
from app.schemas.stars import StarsInvoiceCreateOut
from app.services import card_offer_service, shop_product_service

router = APIRouter(prefix="/card-offers", tags=["card-offers"])
admin_router = APIRouter(prefix="/admin/card-offers", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=list[CardOfferOut])
async def list_offers(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await card_offer_service.list_live(db, user)


@router.post("/seen")
async def offers_seen(body: CardOffersSeenIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """«Карты ⭐» was opened — these players get the «осталось 3 часа» reminder."""
    await card_offer_service.mark_viewed(db, user, body.ids)
    return {"ok": True}


@router.post("/{offer_id}/stars-invoice", response_model=StarsInvoiceCreateOut)
async def offer_invoice(offer_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await shop_product_service.create_invoice(db, user, *await card_offer_service.stars_order(db, user, offer_id))


@admin_router.get("", response_model=list[CardOfferAdminOut])
async def admin_list(db: AsyncSession = Depends(get_db)):
    return await card_offer_service.admin_list(db)


@admin_router.post("", response_model=CardOfferAdminOut)
async def admin_create(body: CardOfferAdminIn, db: AsyncSession = Depends(get_db)):
    return await card_offer_service.admin_create(db, body)


@admin_router.put("/{offer_id}", response_model=CardOfferAdminOut)
async def admin_update(offer_id: int, body: CardOfferAdminIn, db: AsyncSession = Depends(get_db)):
    return await card_offer_service.admin_update(db, offer_id, body)


@admin_router.post("/{offer_id}/announce", response_model=CardOfferAnnounceOut)
async def admin_announce(offer_id: int, db: AsyncSession = Depends(get_db)):
    return CardOfferAnnounceOut(sent=await card_offer_service.admin_announce(db, offer_id))


@admin_router.delete("/{offer_id}")
async def admin_delete(offer_id: int, db: AsyncSession = Depends(get_db)):
    await card_offer_service.admin_delete(db, offer_id)
    return {"deleted": True}
