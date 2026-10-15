"""Admin: every coin transaction of every user, paginated and filterable
(user, type, direction, period), with the totals of the filtered set."""
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.pagination import PageParams
from app.database import get_db
from app.models.enums import TransactionType
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.schemas.transaction import CoinTransactionOut

router = APIRouter(prefix="/admin/transactions", tags=["admin"], dependencies=[Depends(get_current_admin)])


class AdminTransactionOut(CoinTransactionOut):
    user_id: int
    user_name: str
    username: Optional[str] = None
    telegram_id: Optional[int] = None


class AdminTransactionsPage(BaseModel):
    items: list[AdminTransactionOut]
    total: int
    page: int
    page_size: int
    pages: int
    income: int
    spent: int


@router.get("", response_model=AdminTransactionsPage)
async def list_transactions(
    params: PageParams = Depends(),
    user_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None, max_length=64, description="Имя, @username или Telegram ID"),
    type: Optional[TransactionType] = Query(None),
    direction: Optional[Literal["income", "spend"]] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if user_id is not None:
        conditions.append(CoinTransaction.user_id == user_id)
    if search:
        term = search.strip().lstrip("@")
        user_filter = [User.username.ilike(f"%{term}%"), User.first_name.ilike(f"%{term}%"), User.last_name.ilike(f"%{term}%")]
        if term.isdigit():
            user_filter += [User.telegram_id == int(term), User.id == int(term)]
        conditions.append(CoinTransaction.user_id.in_(select(User.id).where(or_(*user_filter))))
    if type is not None:
        conditions.append(CoinTransaction.type == type)
    if direction == "income":
        conditions.append(CoinTransaction.amount > 0)
    elif direction == "spend":
        conditions.append(CoinTransaction.amount < 0)
    if date_from is not None:
        conditions.append(CoinTransaction.created_at >= date_from)
    if date_to is not None:
        conditions.append(CoinTransaction.created_at <= date_to)

    totals = (await db.execute(
        select(
            func.count(CoinTransaction.id),
            func.coalesce(func.sum(CoinTransaction.amount).filter(CoinTransaction.amount > 0), 0),
            func.coalesce(func.sum(CoinTransaction.amount).filter(CoinTransaction.amount < 0), 0),
        ).where(*conditions)
    )).one()
    total, income, spent = int(totals[0]), int(totals[1]), int(totals[2])
    rows = (await db.execute(
        select(CoinTransaction, User).join(User, User.id == CoinTransaction.user_id).where(*conditions)
        .order_by(CoinTransaction.created_at.desc(), CoinTransaction.id.desc())
        .offset(params.offset).limit(params.page_size)
    )).all()
    items = [
        AdminTransactionOut(
            **CoinTransactionOut.model_validate(tx).model_dump(), user_id=user.id, user_name=user.full_display_name(),
            username=user.username, telegram_id=user.telegram_id,
        )
        for tx, user in rows
    ]
    pages = max(1, (total + params.page_size - 1) // params.page_size)
    return AdminTransactionsPage(
        items=items, total=total, page=params.page, page_size=params.page_size, pages=pages, income=income, spent=-spent,
    )
