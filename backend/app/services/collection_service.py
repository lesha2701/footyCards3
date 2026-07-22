from typing import List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import Page, PageParams
from app.models.card import UserCard
from app.models.enums import RARITY_ORDER, TransactionType
from app.models.player import Player
from app.models.user import User
from app.schemas.collection import CollectionFilterParams, UserCardListItem
from app.services.wallet_service import credit_coins, lock_user_for_update


async def _duplicate_counts(db: AsyncSession, user_id: int) -> dict[int, int]:
    result = await db.execute(
        select(UserCard.player_id, func.count(UserCard.id))
        .where(UserCard.owner_id == user_id)
        .group_by(UserCard.player_id)
    )
    return {player_id: count for player_id, count in result.all()}


async def list_user_cards(
    db: AsyncSession, user_id: int, filters: CollectionFilterParams, params: PageParams
) -> Page[UserCardListItem]:
    query = select(UserCard).where(UserCard.owner_id == user_id).options(joinedload(UserCard.player))
    count_query = select(func.count(UserCard.id)).where(UserCard.owner_id == user_id)

    if filters.rarity:
        query = query.join(Player).where(Player.rarity.in_(filters.rarity))
        count_query = count_query.join(Player).where(Player.rarity.in_(filters.rarity))
    else:
        query = query.join(Player)
        count_query = count_query.join(Player)

    if filters.country:
        query = query.where(Player.country == filters.country)
        count_query = count_query.where(Player.country == filters.country)
    if filters.club:
        query = query.where(Player.club == filters.club)
        count_query = count_query.where(Player.club == filters.club)
    if filters.position:
        query = query.where(Player.position == filters.position)
        count_query = count_query.where(Player.position == filters.position)
    if filters.min_rating is not None:
        query = query.where(Player.rating >= filters.min_rating)
        count_query = count_query.where(Player.rating >= filters.min_rating)
    if filters.max_rating is not None:
        query = query.where(Player.rating <= filters.max_rating)
        count_query = count_query.where(Player.rating <= filters.max_rating)
    if filters.search:
        pattern = f"%{filters.search.lower()}%"
        query = query.where(func.lower(Player.display_name).like(pattern))
        count_query = count_query.where(func.lower(Player.display_name).like(pattern))

    total = (await db.execute(count_query)).scalar_one()

    if filters.sort_by == "rating":
        order_col = Player.rating
    elif filters.sort_by == "rarity":
        order_col = Player.rating  # secondary tiebreaker; rarity ordered below in python
    else:
        order_col = UserCard.acquired_at

    query = query.order_by(order_col.desc() if filters.sort_dir == "desc" else order_col.asc())
    query = query.offset(params.offset).limit(params.page_size)

    cards: List[UserCard] = (await db.execute(query)).unique().scalars().all()

    if filters.sort_by == "rarity":
        cards.sort(key=lambda c: RARITY_ORDER[c.player.rarity], reverse=(filters.sort_dir == "desc"))

    dup_counts = await _duplicate_counts(db, user_id)
    items = []
    for card in cards:
        item = UserCardListItem.model_validate(card)
        item.duplicate_count = dup_counts.get(card.player_id, 1)
        items.append(item)

    return Page.build(items, total, params)


async def collection_stats(db: AsyncSession, user_id: int) -> dict:
    total = (await db.execute(select(func.count(UserCard.id)).where(UserCard.owner_id == user_id))).scalar_one()
    unique = (
        await db.execute(select(func.count(func.distinct(UserCard.player_id))).where(UserCard.owner_id == user_id))
    ).scalar_one()
    rows = await db.execute(
        select(Player.rarity, func.count(UserCard.id))
        .join(UserCard, UserCard.player_id == Player.id)
        .where(UserCard.owner_id == user_id)
        .group_by(Player.rarity)
    )
    by_rarity = {rarity.value: count for rarity, count in rows.all()}
    return {"unique_players": unique, "total_cards": total, "by_rarity": by_rarity}


async def _assert_sellable(db: AsyncSession, user_id: int, card: UserCard, confirm_last_copy: bool) -> None:
    if card is None:
        raise NotFoundError("Card not found")
    if card.owner_id != user_id:
        raise ForbiddenError("This card does not belong to you")
    if card.is_locked_by_admin:
        raise ConflictError("Card is locked by an administrator")
    if card.is_locked_in_trade:
        raise ConflictError("Card is locked in an active trade")
    if card.is_in_lineup:
        raise ConflictError("Card is used in an active lineup")

    remaining = (
        await db.execute(
            select(func.count(UserCard.id)).where(
                UserCard.owner_id == user_id, UserCard.player_id == card.player_id
            )
        )
    ).scalar_one()
    if remaining <= 1 and not confirm_last_copy:
        raise ConflictError(
            "This is your last copy of this player. Pass confirm_last_copy=true to sell it anyway.",
            details={"requires_confirmation": True},
        )


async def sell_cards(db: AsyncSession, user: User, user_card_ids: List[int], confirm_last_copy: bool) -> dict:
    locked_user = await lock_user_for_update(db, user.id)

    result = await db.execute(
        select(UserCard).where(UserCard.id.in_(user_card_ids)).options(joinedload(UserCard.player))
    )
    cards = result.unique().scalars().all()
    if len(cards) != len(set(user_card_ids)):
        raise NotFoundError("One or more cards not found")

    total_value = 0
    for card in cards:
        await _assert_sellable(db, user.id, card, confirm_last_copy)
        total_value += card.player.quick_sell_price

    for card in cards:
        await db.delete(card)

    await credit_coins(
        db,
        locked_user,
        total_value,
        TransactionType.card_sale,
        f"Продажа {len(cards)} карточ(и/ек) системе",
    )
    await db.commit()
    await db.refresh(locked_user)
    return {"sold_count": len(cards), "coins_earned": total_value, "new_balance": locked_user.balance}
