import random
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.card import UserCard
from app.models.card_upgrade import CardUpgradeAttempt, CardUpgradeRule
from app.models.enums import RARITY_ORDER, CardSource, Rarity, TransactionType
from app.models.user import User
from app.schemas.card_upgrade import CardUpgradeResultOut, UserCardOut
from app.services.card_creation import create_user_card
from app.services.collection_service import grant_collection_rewards_for_new_cards
from app.services.pack_service import pick_random_player
from app.services.wallet_service import debit_coins, lock_user_for_update


async def list_rules(db: AsyncSession) -> list[CardUpgradeRule]:
    result = await db.execute(select(CardUpgradeRule).order_by(CardUpgradeRule.from_rarity, CardUpgradeRule.to_rarity))
    return list(result.scalars().all())


async def _get_active_rule(db: AsyncSession, from_rarity: Rarity, to_rarity: Rarity) -> CardUpgradeRule:
    result = await db.execute(
        select(CardUpgradeRule).where(
            CardUpgradeRule.from_rarity == from_rarity,
            CardUpgradeRule.to_rarity == to_rarity,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None or not rule.is_active:
        raise ConflictError("This upgrade path is not available")
    return rule


async def _existing_attempt(db: AsyncSession, user_id: int, idempotency_key: Optional[str]) -> Optional[CardUpgradeAttempt]:
    if not idempotency_key:
        return None
    result = await db.execute(
        select(CardUpgradeAttempt).where(
            CardUpgradeAttempt.user_id == user_id, CardUpgradeAttempt.idempotency_key == idempotency_key
        )
    )
    return result.scalar_one_or_none()


async def _attempt_to_out(db: AsyncSession, attempt: CardUpgradeAttempt, new_balance: Optional[int] = None) -> CardUpgradeResultOut:
    new_card_out = None
    if attempt.result_card_id is not None:
        result = await db.execute(
            select(UserCard).where(UserCard.id == attempt.result_card_id).options(joinedload(UserCard.player))
        )
        card = result.scalar_one_or_none()
        if card is not None:
            new_card_out = UserCardOut.model_validate(card)

    if new_balance is None:
        user = await db.get(User, attempt.user_id)
        new_balance = user.balance if user else 0

    return CardUpgradeResultOut(
        success=attempt.success,
        from_rarity=attempt.from_rarity,
        to_rarity=attempt.to_rarity,
        coin_cost=attempt.coin_cost,
        new_card=new_card_out,
        new_balance=new_balance,
    )


async def upgrade_card(
    db: AsyncSession,
    user: User,
    user_card_id: int,
    target_rarity: Rarity,
    idempotency_key: Optional[str],
) -> CardUpgradeResultOut:
    existing = await _existing_attempt(db, user.id, idempotency_key)
    if existing is not None:
        return await _attempt_to_out(db, existing)

    locked_user = await lock_user_for_update(db, user.id)

    result = await db.execute(
        select(UserCard).where(UserCard.id == user_card_id).options(joinedload(UserCard.player))
    )
    card = result.scalar_one_or_none()
    if card is None or card.owner_id != locked_user.id:
        raise NotFoundError("Card not found")
    if card.is_locked_by_admin or card.is_locked_in_trade or card.is_in_lineup:
        raise ConflictError("This card is locked and cannot be upgraded")

    from_rarity = card.player.rarity
    if RARITY_ORDER[target_rarity] <= RARITY_ORDER[from_rarity]:
        raise ConflictError("Target rarity must be higher than the card's current rarity")

    rule = await _get_active_rule(db, from_rarity, target_rarity)

    await debit_coins(
        db, locked_user, rule.coin_cost, TransactionType.card_upgrade,
        f"Апгрейд карточки: {from_rarity.value} → {target_rarity.value}",
        related_object_type="user_card", related_object_id=card.id,
    )

    source_player_id = card.player_id
    await db.delete(card)
    await db.flush()

    success = random.random() < float(rule.success_chance)
    result_card_id = None
    if success:
        new_player = await pick_random_player(db, target_rarity)
        new_card = await create_user_card(db, locked_user.id, new_player.id, CardSource.card_upgrade)
        result_card_id = new_card.id
        await grant_collection_rewards_for_new_cards(db, locked_user, [new_player.id])

    attempt = CardUpgradeAttempt(
        user_id=locked_user.id,
        source_player_id=source_player_id,
        from_rarity=from_rarity,
        to_rarity=target_rarity,
        coin_cost=rule.coin_cost,
        success=success,
        result_card_id=result_card_id,
        idempotency_key=idempotency_key,
        created_at=datetime.now(timezone.utc),
    )
    db.add(attempt)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if idempotency_key:
            existing = await _existing_attempt(db, user.id, idempotency_key)
            if existing is not None:
                return await _attempt_to_out(db, existing)
        raise

    await db.refresh(locked_user)
    return await _attempt_to_out(db, attempt, new_balance=locked_user.balance)
