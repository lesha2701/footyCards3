from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.card_collection import CardCollection
from app.models.player import Player
from app.models.user import User
from app.schemas.card_collection import (
    CardCollectionCreate,
    CardCollectionOut,
    CardCollectionUpdate,
    SetCollectionPlayersRequest,
)
from app.schemas.player import PlayerOut
from app.services.admin_log_service import log_action
from app.services.image_service import delete_collection_image, save_collection_image

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


@router.post("/{collection_id}/image", response_model=CardCollectionOut)
async def upload_collection_image(
    collection_id: int, request: Request, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    collection = await _get_collection_or_404(db, collection_id)
    old_path = collection.image_path
    new_path = await save_collection_image(file, collection.name)
    collection.image_path = new_path
    db.add(collection)
    delete_collection_image(old_path)
    await log_action(
        db, admin.id, "upload_card_collection_image", "card_collection", collection_id,
        old_value={"image_path": old_path}, new_value={"image_path": new_path},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(collection)
    return CardCollectionOut.model_validate(collection)


@router.get("/{collection_id}/players", response_model=list[PlayerOut])
async def list_collection_players(collection_id: int, db: AsyncSession = Depends(get_db)):
    await _get_collection_or_404(db, collection_id)
    result = await db.execute(select(Player).where(Player.collection_id == collection_id))
    return [PlayerOut.model_validate(p) for p in result.scalars().all()]


@router.put("/{collection_id}/players", response_model=list[PlayerOut])
async def set_collection_players(
    collection_id: int, payload: SetCollectionPlayersRequest, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    await _get_collection_or_404(db, collection_id)
    player_ids = set(payload.player_ids)

    if player_ids:
        found = (await db.execute(select(func.count(Player.id)).where(Player.id.in_(player_ids)))).scalar_one()
        if found != len(player_ids):
            raise NotFoundError("One or more players not found")

    old_members = (
        await db.execute(select(Player.id).where(Player.collection_id == collection_id))
    ).scalars().all()

    await db.execute(
        update(Player).where(Player.collection_id == collection_id, Player.id.notin_(player_ids)).values(collection_id=None)
    )
    if player_ids:
        await db.execute(update(Player).where(Player.id.in_(player_ids)).values(collection_id=collection_id))

    await log_action(
        db, admin.id, "set_card_collection_players", "card_collection", collection_id,
        old_value={"player_ids": sorted(old_members)}, new_value={"player_ids": sorted(player_ids)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    result = await db.execute(select(Player).where(Player.collection_id == collection_id))
    return [PlayerOut.model_validate(p) for p in result.scalars().all()]
