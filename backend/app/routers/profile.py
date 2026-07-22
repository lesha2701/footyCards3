from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.schemas.profile import ProfilePrivateOut
from app.schemas.transaction import CoinTransactionOut
from app.services.profile_service import get_private_profile

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me", response_model=ProfilePrivateOut)
async def read_my_profile(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await get_private_profile(db, user)


@router.get("/transactions", response_model=Page[CoinTransactionOut])
async def read_my_transactions(
    params: PageParams = Depends(), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    from sqlalchemy import func

    total = (
        await db.execute(select(func.count(CoinTransaction.id)).where(CoinTransaction.user_id == user.id))
    ).scalar_one()
    result = await db.execute(
        select(CoinTransaction)
        .where(CoinTransaction.user_id == user.id)
        .order_by(CoinTransaction.created_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    items = [CoinTransactionOut.model_validate(t) for t in result.scalars().all()]
    return Page.build(items, total, params)
