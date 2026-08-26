from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InsufficientBalanceError
from app.models.club import Club
from app.models.club_budget import ClubBudgetTransaction
from app.models.enums import ClubBudgetTransactionType


async def credit_club_budget(
    db: AsyncSession,
    club: Club,
    amount: int,
    tx_type: ClubBudgetTransactionType,
    description: str = "",
    related_object_type: Optional[str] = None,
    related_object_id: Optional[int] = None,
) -> ClubBudgetTransaction:
    if amount < 0:
        raise ValueError("credit_club_budget amount must be >= 0")
    balance_before = club.budget
    club.budget = balance_before + amount
    tx = ClubBudgetTransaction(
        club_id=club.id, amount=amount, balance_before=balance_before, balance_after=club.budget,
        type=tx_type, description=description, related_object_type=related_object_type, related_object_id=related_object_id,
    )
    db.add(tx)
    db.add(club)
    return tx


async def debit_club_budget(
    db: AsyncSession,
    club: Club,
    amount: int,
    tx_type: ClubBudgetTransactionType,
    description: str = "",
    related_object_type: Optional[str] = None,
    related_object_id: Optional[int] = None,
) -> ClubBudgetTransaction:
    if amount < 0:
        raise ValueError("debit_club_budget amount must be >= 0")
    if club.budget < amount:
        raise InsufficientBalanceError("Недостаточно средств в бюджете клуба", details={"budget": club.budget, "required": amount})
    balance_before = club.budget
    club.budget = balance_before - amount
    tx = ClubBudgetTransaction(
        club_id=club.id, amount=-amount, balance_before=balance_before, balance_after=club.budget,
        type=tx_type, description=description, related_object_type=related_object_type, related_object_id=related_object_id,
    )
    db.add(tx)
    db.add(club)
    return tx
