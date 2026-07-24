from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.card_collection import CardCollection
from app.models.user import User
from app.schemas.card_collection import CardCollectionPublicOut

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("", response_model=list[CardCollectionPublicOut])
async def list_active_collections(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    result = await db.execute(
        select(CardCollection).where(CardCollection.is_active.is_(True)).order_by(CardCollection.sort_order)
    )
    return [CardCollectionPublicOut.model_validate(c) for c in result.scalars().all()]
