from typing import Iterable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import Page, PageParams
from app.models.card import UserCard
from app.models.card_collection import CardCollection, UserCollectionReward
from app.models.enums import RARITY_ORDER, CardSource, NotificationType, TransactionType
from app.models.pack import Pack
from app.models.player import Player
from app.models.user import User
from app.schemas.collection import (
    AlbumCollectionDetailOut,
    AlbumCollectionSummaryOut,
    AlbumOverviewOut,
    AlbumPlayerOut,
    CollectionFilterParams,
    UserCardListItem,
)
from app.schemas.pack import CollectionRewardGrantOut
from app.schemas.player import PlayerOut
from app.services import notification_service
from app.services.wallet_service import credit_coins, lock_user_for_update

OTHER_COLLECTION_ID = -1


async def _duplicate_counts(db: AsyncSession, user_id: int) -> dict[int, int]:
    result = await db.execute(
        select(UserCard.player_id, func.count(UserCard.id))
        .where(UserCard.owner_id == user_id)
        .group_by(UserCard.player_id)
    )
    return {player_id: count for player_id, count in result.all()}


async def list_user_cards(
    db: AsyncSession, user_id: int, filters: CollectionFilterParams, params: PageParams, exclude_hidden: bool = False
) -> Page[UserCardListItem]:
    query = select(UserCard).where(UserCard.owner_id == user_id).options(joinedload(UserCard.player))

    if exclude_hidden:
        query = query.where(UserCard.hidden_from_trade.is_(False))

    if filters.rarity:
        query = query.join(Player).where(Player.rarity.in_(filters.rarity))
    else:
        query = query.join(Player)

    if filters.country:
        query = query.where(Player.country == filters.country)
    if filters.club:
        query = query.where(Player.club == filters.club)
    if filters.position:
        query = query.where(Player.position == filters.position)
    if filters.min_rating is not None:
        query = query.where(Player.rating >= filters.min_rating)
    if filters.max_rating is not None:
        query = query.where(Player.rating <= filters.max_rating)
    if filters.collection_id is not None:
        query = query.where(Player.collection_id == filters.collection_id)
    if filters.search:
        pattern = f"%{filters.search.lower()}%"
        query = query.where(func.lower(Player.display_name).like(pattern))

    if filters.sort_by == "rating":
        order_col = Player.rating
    elif filters.sort_by == "rarity":
        order_col = Player.rating  # secondary tiebreaker; rarity ordered below in python
    else:
        order_col = UserCard.acquired_at

    query = query.order_by(order_col.desc() if filters.sort_dir == "desc" else order_col.asc())

    # Pagination and totals are computed after collapsing duplicate copies of
    # the same player (below), not at the SQL level, so LIMIT/OFFSET can't be
    # pushed into this query — the whole filtered set has to be fetched first.
    all_cards: List[UserCard] = (await db.execute(query)).unique().scalars().all()

    if filters.sort_by == "rarity":
        all_cards.sort(key=lambda c: RARITY_ORDER[c.player.rarity], reverse=(filters.sort_dir == "desc"))

    # A user can own several copies of the same player (duplicates); the
    # collection list should show each player once, with duplicate_count
    # conveying how many copies are owned — not one row per physical card.
    representative_by_player: dict[int, UserCard] = {}
    for card in all_cards:
        representative_by_player.setdefault(card.player_id, card)
    unique_cards = list(representative_by_player.values())

    total = len(unique_cards)
    page_cards = unique_cards[params.offset : params.offset + params.page_size]

    dup_counts = await _duplicate_counts(db, user_id)
    items = []
    for card in page_cards:
        item = UserCardListItem.model_validate(card)
        item.duplicate_count = dup_counts.get(card.player_id, 1)
        items.append(item)

    return Page.build(items, total, params)


async def set_card_hidden(db: AsyncSession, user_id: int, user_card_id: int, hidden: bool) -> UserCardListItem:
    card = await db.get(UserCard, user_card_id, options=[joinedload(UserCard.player)])
    if card is None:
        raise NotFoundError("Card not found")
    if card.owner_id != user_id:
        raise ForbiddenError("This card does not belong to you")

    card.hidden_from_trade = hidden
    db.add(card)
    await db.commit()
    await db.refresh(card)

    dup_counts = await _duplicate_counts(db, user_id)
    item = UserCardListItem.model_validate(card)
    item.duplicate_count = dup_counts.get(card.player_id, 1)
    return item


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


async def _collection_progress(db: AsyncSession, user_id: int, collection_id: Optional[int]) -> tuple[int, int]:
    """`collection_id=None` means the synthetic "Other players" bucket
    (active players with no `collection_id` assigned)."""
    condition = Player.collection_id.is_(None) if collection_id is None else Player.collection_id == collection_id
    total = (
        await db.execute(select(func.count(Player.id)).where(condition, Player.is_active.is_(True)))
    ).scalar_one()
    owned = (
        await db.execute(
            select(func.count(func.distinct(UserCard.player_id)))
            .join(Player, Player.id == UserCard.player_id)
            .where(UserCard.owner_id == user_id, condition, Player.is_active.is_(True))
        )
    ).scalar_one()
    return owned, total


async def _reward_claimed(db: AsyncSession, user_id: int, collection_id: int) -> bool:
    return (
        await db.execute(
            select(UserCollectionReward.id).where(
                UserCollectionReward.user_id == user_id, UserCollectionReward.collection_id == collection_id
            )
        )
    ).scalar_one_or_none() is not None


async def _pack_name(db: AsyncSession, pack_id: Optional[int]) -> Optional[str]:
    if not pack_id:
        return None
    pack = await db.get(Pack, pack_id)
    return pack.name if pack else None


async def grant_collection_rewards_for_new_cards(
    db: AsyncSession, user: User, player_ids: Iterable[int]
) -> List[CollectionRewardGrantOut]:
    """Call after any operation that changes which players `user` owns —
    both new-card creation (pack opens, daily reward, card upgrade) and
    incoming trade transfers. `player_ids` is every player_id touched by
    that operation; passing already-owned duplicates alongside genuinely
    new ones is harmless (naturally idempotent via `UserCollectionReward`'s
    unique constraint + the already-granted check below), so callers don't
    need to track which cards were actually "new".

    Precondition: `user` must already be a row-locked User (every call site
    already holds the lock for its own balance-mutating work) — this
    function does not lock it itself.
    """
    player_ids = set(player_ids)
    if not player_ids:
        return []

    candidate_ids = (
        await db.execute(
            select(Player.collection_id)
            .distinct()
            .join(CardCollection, CardCollection.id == Player.collection_id)
            .where(Player.id.in_(player_ids), CardCollection.is_active.is_(True))
        )
    ).scalars().all()
    # Players with collection_id IS NULL (the synthetic "Other players"
    # bucket) are deliberately excluded — there's no CardCollection row to
    # hang a reward off, by design.
    if not candidate_ids:
        return []

    already_granted = set(
        (
            await db.execute(
                select(UserCollectionReward.collection_id).where(
                    UserCollectionReward.user_id == user.id,
                    UserCollectionReward.collection_id.in_(candidate_ids),
                )
            )
        ).scalars().all()
    )
    pending_ids = [cid for cid in candidate_ids if cid not in already_granted]
    if not pending_ids:
        return []

    grants: List[CollectionRewardGrantOut] = []
    for collection_id in pending_ids:
        collection = await db.get(CardCollection, collection_id)
        if collection is None:
            continue

        owned, total = await _collection_progress(db, user.id, collection_id)
        if total == 0 or owned < total:
            continue

        db.add(
            UserCollectionReward(
                user_id=user.id, collection_id=collection_id,
                reward_coins=collection.reward_coins, reward_pack_id=collection.reward_pack_id,
            )
        )

        if collection.reward_coins > 0:
            await credit_coins(
                db, user, collection.reward_coins, TransactionType.collection_reward,
                f"Коллекция «{collection.name}» собрана полностью",
                related_object_type="card_collection", related_object_id=collection_id,
            )

        granted_pack = None
        if collection.reward_pack_id:
            from app.services.pack_service import grant_bonus_pack_opening

            granted_pack = await grant_bonus_pack_opening(
                db, user, collection.reward_pack_id,
                idempotency_prefix=f"collection-reward-{user.id}-{collection_id}",
                source=CardSource.collection_reward,
            )

        pack_note = f" и бонусный пак «{granted_pack.pack.name}»" if granted_pack else ""
        await notification_service.notify(
            db, user.id, NotificationType.collection_completed,
            "🎉 Коллекция собрана!",
            f"Ты собрал(а) всех футболистов коллекции «{collection.name}»! "
            f"Получено {collection.reward_coins} монет{pack_note}.",
            related_object_type="card_collection", related_object_id=collection_id,
        )

        grants.append(
            CollectionRewardGrantOut(
                collection_id=collection_id, collection_name=collection.name,
                reward_coins=collection.reward_coins, granted_pack=granted_pack,
            )
        )

    return grants


async def get_album_overview(db: AsyncSession, user_id: int, search: Optional[str] = None) -> AlbumOverviewOut:
    pattern = f"%{search.lower()}%" if search else None

    collections = (
        await db.execute(
            select(CardCollection).where(CardCollection.is_active.is_(True)).order_by(CardCollection.sort_order)
        )
    ).scalars().all()

    summaries: List[AlbumCollectionSummaryOut] = []
    for collection in collections:
        owned, total = await _collection_progress(db, user_id, collection.id)
        if total == 0:
            continue
        if pattern:
            has_match = (
                await db.execute(
                    select(func.count(Player.id)).where(
                        Player.collection_id == collection.id, Player.is_active.is_(True),
                        func.lower(Player.display_name).like(pattern),
                    )
                )
            ).scalar_one()
            if not has_match:
                continue

        summaries.append(
            AlbumCollectionSummaryOut(
                id=collection.id, name=collection.name, description=collection.description,
                image_path=collection.image_path, owned_count=owned, total_count=total,
                is_complete=owned >= total, reward_coins=collection.reward_coins,
                reward_pack_name=await _pack_name(db, collection.reward_pack_id),
                reward_claimed=await _reward_claimed(db, user_id, collection.id),
            )
        )

    other_owned, other_total = await _collection_progress(db, user_id, None)
    if other_total > 0:
        include_other = True
        if pattern:
            other_match = (
                await db.execute(
                    select(func.count(Player.id)).where(
                        Player.collection_id.is_(None), Player.is_active.is_(True),
                        func.lower(Player.display_name).like(pattern),
                    )
                )
            ).scalar_one()
            include_other = other_match > 0
        if include_other:
            summaries.append(
                AlbumCollectionSummaryOut(
                    id=OTHER_COLLECTION_ID, name="Другие игроки", description="",
                    image_path=None, owned_count=other_owned, total_count=other_total,
                    is_complete=other_owned >= other_total, reward_coins=0,
                    reward_pack_name=None, reward_claimed=False,
                )
            )

    overall_total = (await db.execute(select(func.count(Player.id)).where(Player.is_active.is_(True)))).scalar_one()
    overall_owned = (
        await db.execute(
            select(func.count(func.distinct(UserCard.player_id)))
            .join(Player, Player.id == UserCard.player_id)
            .where(UserCard.owner_id == user_id, Player.is_active.is_(True))
        )
    ).scalar_one()

    return AlbumOverviewOut(collections=summaries, overall_owned=overall_owned, overall_total=overall_total)


async def get_album_collection_detail(
    db: AsyncSession, user_id: int, collection_id: int, search: Optional[str] = None
) -> AlbumCollectionDetailOut:
    if collection_id == OTHER_COLLECTION_ID:
        name, description, image_path = "Другие игроки", "", None
        reward_coins, reward_pack_name = 0, None
        player_query = select(Player).where(Player.collection_id.is_(None), Player.is_active.is_(True))
    else:
        collection = await db.get(CardCollection, collection_id)
        if collection is None or not collection.is_active:
            raise NotFoundError("Collection not found")
        name, description, image_path = collection.name, collection.description, collection.image_path
        reward_coins = collection.reward_coins
        reward_pack_name = await _pack_name(db, collection.reward_pack_id)
        player_query = select(Player).where(Player.collection_id == collection_id, Player.is_active.is_(True))

    owned, total = await _collection_progress(db, user_id, None if collection_id == OTHER_COLLECTION_ID else collection_id)

    if search:
        player_query = player_query.where(func.lower(Player.display_name).like(f"%{search.lower()}%"))
    players = (await db.execute(player_query.order_by(Player.display_name))).scalars().all()
    player_ids = [p.id for p in players]

    owned_cards: dict[int, UserCard] = {}
    dup_counts: dict[int, int] = {}
    if player_ids:
        cards_result = await db.execute(
            select(UserCard)
            .where(UserCard.owner_id == user_id, UserCard.player_id.in_(player_ids))
            .options(joinedload(UserCard.player))
        )
        for card in cards_result.unique().scalars().all():
            dup_counts[card.player_id] = dup_counts.get(card.player_id, 0) + 1
            owned_cards.setdefault(card.player_id, card)

    slots: List[AlbumPlayerOut] = []
    for player in players:
        card = owned_cards.get(player.id)
        card_item = None
        if card is not None:
            card_item = UserCardListItem.model_validate(card)
            card_item.duplicate_count = dup_counts.get(player.id, 1)
        slots.append(
            AlbumPlayerOut(
                player=PlayerOut.model_validate(player), owned=card is not None,
                duplicate_count=dup_counts.get(player.id, 0), card=card_item,
            )
        )

    return AlbumCollectionDetailOut(
        id=collection_id, name=name, description=description, image_path=image_path,
        reward_coins=reward_coins, reward_pack_name=reward_pack_name,
        owned_count=owned, total_count=total, is_complete=owned >= total,
        reward_claimed=False if collection_id == OTHER_COLLECTION_ID else await _reward_claimed(db, user_id, collection_id),
        players=slots,
    )
