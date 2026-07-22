from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.card import UserCard
from app.models.enums import TransactionType
from app.models.player import Player
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.schemas.admin import AdminUserOut, BalanceAdjustRequest, GrantCardRequest, ResetLimitsResponse
from app.schemas.card import UserCardOut
from app.schemas.transaction import CoinTransactionOut
from app.services.admin_log_service import log_action
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update

router = APIRouter(prefix="/admin/users", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=Page[AdminUserOut])
async def list_users(
    search: Optional[str] = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    query = select(User)
    count_query = select(func.count(User.id))
    if search:
        pattern = f"%{search}%"
        condition = User.username.ilike(pattern) | User.first_name.ilike(pattern) | User.last_name.ilike(pattern)
        if search.isdigit():
            condition = condition | (User.telegram_id == int(search)) | (User.id == int(search))
        query = query.where(condition)
        count_query = count_query.where(condition)

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(User.created_at.desc()).offset(params.offset).limit(params.page_size)
    users = (await db.execute(query)).scalars().all()
    return Page.build([AdminUserOut.model_validate(u) for u in users], total, params)


async def _get_user_or_404(db: AsyncSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    return user


@router.get("/{user_id}", response_model=AdminUserOut)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    return await _get_user_or_404(db, user_id)


@router.get("/{user_id}/collection", response_model=Page[UserCardOut])
async def get_user_collection(user_id: int, params: PageParams = Depends(), db: AsyncSession = Depends(get_db)):
    await _get_user_or_404(db, user_id)
    total = (await db.execute(select(func.count(UserCard.id)).where(UserCard.owner_id == user_id))).scalar_one()
    result = await db.execute(
        select(UserCard)
        .where(UserCard.owner_id == user_id)
        .options(joinedload(UserCard.player))
        .order_by(UserCard.acquired_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    cards = result.unique().scalars().all()
    return Page.build([UserCardOut.model_validate(c) for c in cards], total, params)


@router.get("/{user_id}/transactions", response_model=Page[CoinTransactionOut])
async def get_user_transactions(user_id: int, params: PageParams = Depends(), db: AsyncSession = Depends(get_db)):
    await _get_user_or_404(db, user_id)
    total = (
        await db.execute(select(func.count(CoinTransaction.id)).where(CoinTransaction.user_id == user_id))
    ).scalar_one()
    result = await db.execute(
        select(CoinTransaction)
        .where(CoinTransaction.user_id == user_id)
        .order_by(CoinTransaction.created_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    return Page.build([CoinTransactionOut.model_validate(t) for t in result.scalars().all()], total, params)


@router.post("/{user_id}/balance", response_model=AdminUserOut)
async def adjust_balance(
    user_id: int,
    payload: BalanceAdjustRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    await _get_user_or_404(db, user_id)
    locked_user = await lock_user_for_update(db, user_id)
    old_balance = locked_user.balance

    if payload.amount >= 0:
        await credit_coins(db, locked_user, payload.amount, TransactionType.admin_adjustment, payload.description)
    else:
        await debit_coins(db, locked_user, -payload.amount, TransactionType.admin_adjustment, payload.description)

    await log_action(
        db, admin.id, "adjust_balance", "user", user_id,
        old_value={"balance": old_balance}, new_value={"balance": locked_user.balance, "delta": payload.amount},
        ip_address=request.client.host if request.client else None, extra=payload.description,
    )
    await db.commit()
    await db.refresh(locked_user)
    return locked_user


@router.post("/{user_id}/ban", response_model=AdminUserOut)
async def ban_user(user_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    user = await _get_user_or_404(db, user_id)
    user.is_banned = True
    db.add(user)
    await log_action(db, admin.id, "ban_user", "user", user_id, ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/{user_id}/unban", response_model=AdminUserOut)
async def unban_user(user_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    user = await _get_user_or_404(db, user_id)
    user.is_banned = False
    db.add(user)
    await log_action(db, admin.id, "unban_user", "user", user_id, ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/{user_id}/cards/grant", response_model=UserCardOut)
async def grant_card(
    user_id: int, payload: GrantCardRequest, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    from app.models.enums import CardSource
    from app.services.card_creation import create_user_card

    await _get_user_or_404(db, user_id)
    player = await db.get(Player, payload.player_id)
    if not player:
        raise NotFoundError("Player not found")

    card = await create_user_card(db, user_id, player.id, CardSource.admin_grant, admin.id)
    card.player = player

    await log_action(
        db, admin.id, "grant_card", "user_card", card.id,
        new_value={"user_id": user_id, "player_id": player.id},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return card


@router.delete("/{user_id}/cards/{card_id}")
async def delete_card(
    user_id: int, card_id: int, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    from app.core.exceptions import ConflictError

    card = await db.get(UserCard, card_id)
    if not card or card.owner_id != user_id:
        raise NotFoundError("Card not found for this user")
    if card.is_locked_in_trade:
        raise ConflictError("Cancel the pending trade before deleting this card")

    await log_action(
        db, admin.id, "delete_card", "user_card", card_id,
        old_value={"user_id": user_id, "player_id": card.player_id},
        ip_address=request.client.host if request.client else None,
    )
    await db.delete(card)
    await db.commit()
    return {"status": "ok"}


@router.post("/{user_id}/reset-limits", response_model=ResetLimitsResponse)
async def reset_limits(user_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    user = await _get_user_or_404(db, user_id)
    from app.services.game_config_service import get_config

    config = await get_config(db)
    user.match_energy = config.match_daily_energy
    user.memory_rewarded_attempts_today = 0
    db.add(user)
    await log_action(db, admin.id, "reset_limits", "user", user_id, ip_address=request.client.host if request.client else None)
    await db.commit()
    return ResetLimitsResponse()


@router.post("/{user_id}/toggle-reward-block", response_model=AdminUserOut)
async def toggle_reward_block(user_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    user = await _get_user_or_404(db, user_id)
    user.game_rewards_blocked = not user.game_rewards_blocked
    db.add(user)
    await log_action(
        db, admin.id, "toggle_reward_block", "user", user_id,
        new_value={"game_rewards_blocked": user.game_rewards_blocked},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(user)
    return user
