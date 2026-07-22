from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InsufficientBalanceError
from app.models.enums import TransactionType
from app.models.transaction import CoinTransaction
from app.models.user import User


async def lock_user_for_update(db: AsyncSession, user_id: int) -> User:
    """Locks the user row so concurrent balance-mutating requests serialize.

    Requires an active DB transaction (started implicitly by AsyncSession);
    the lock is released on commit/rollback.
    """
    result = await db.execute(select(User).where(User.id == user_id).with_for_update())
    user = result.scalar_one()
    return user


async def credit_coins(
    db: AsyncSession,
    user: User,
    amount: int,
    tx_type: TransactionType,
    description: str = "",
    related_object_type: Optional[str] = None,
    related_object_id: Optional[int] = None,
) -> CoinTransaction:
    if amount < 0:
        raise ValueError("credit_coins amount must be >= 0")
    balance_before = user.balance
    user.balance = balance_before + amount
    tx = CoinTransaction(
        user_id=user.id,
        amount=amount,
        balance_before=balance_before,
        balance_after=user.balance,
        type=tx_type,
        description=description,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
    )
    db.add(tx)
    db.add(user)
    return tx


async def debit_coins(
    db: AsyncSession,
    user: User,
    amount: int,
    tx_type: TransactionType,
    description: str = "",
    related_object_type: Optional[str] = None,
    related_object_id: Optional[int] = None,
) -> CoinTransaction:
    if amount < 0:
        raise ValueError("debit_coins amount must be >= 0")
    if user.balance < amount:
        raise InsufficientBalanceError(
            "Not enough coins",
            details={"balance": user.balance, "required": amount},
        )
    balance_before = user.balance
    user.balance = balance_before - amount
    tx = CoinTransaction(
        user_id=user.id,
        amount=-amount,
        balance_before=balance_before,
        balance_after=user.balance,
        type=tx_type,
        description=description,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
    )
    db.add(tx)
    db.add(user)
    return tx
