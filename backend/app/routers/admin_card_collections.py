from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.card_collection import CardCollection
from app.models.user import User
from app.schemas.card_collection import CardCollectionCreate, CardCollectionOut, CardCollectionUpdate
from app.services.admin_log_service import log_action

router = APIRouter(prefix="/admin/card-collections", tags=["admin"], dependencies=[Depends(get_current_admin)])


async def _get_collection_or_404(db: AsyncSession, collection_id: int) -> CardCollection:
    collection = await db.get(CardCollection, collection_id)
    if not collection:
        raise NotFoundError("Card collection not found")
    return collection


@router.get("", response_model=list[CardCollectionOut])
async def list_all_collections(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CardCollection).order_by(CardCollection.sort_order))
    return [CardCollectionOut.model_validate(c) for c in result.scalars().all()]


@router.post("", response_model=CardCollectionOut)
async def create_collection(payload: CardCollectionCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    collection = CardCollection(**payload.model_dump())
    db.add(collection)
    await db.flush()
    await log_action(db, admin.id, "create_card_collection", "card_collection", collection.id, new_value=payload.model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    await db.commit()
    return CardCollectionOut.model_validate(collection)


@router.put("/{collection_id}", response_model=CardCollectionOut)
async def update_collection(collection_id: int, payload: CardCollectionUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    collection = await _get_collection_or_404(db, collection_id)
    old_value = CardCollectionOut.model_validate(collection).model_dump(mode="json")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(collection, key, value)

    db.add(collection)
    await log_action(
        db, admin.id, "update_card_collection", "card_collection", collection_id, old_value=old_value,
        new_value=payload.model_dump(mode="json", exclude_unset=True),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(collection)
    return CardCollectionOut.model_validate(collection)


@router.post("/{collection_id}/toggle-active", response_model=CardCollectionOut)
async def toggle_collection_active(collection_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    collection = await _get_collection_or_404(db, collection_id)
    collection.is_active = not collection.is_active
    db.add(collection)
    await log_action(db, admin.id, "toggle_card_collection_active", "card_collection", collection_id, new_value={"is_active": collection.is_active}, ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(collection)
    return CardCollectionOut.model_validate(collection)
