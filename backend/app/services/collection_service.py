from types import SimpleNamespace
from typing import Iterable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import Page, PageParams
from app.models.card import UserCard
from app.models.card_collection import CardCollection, UserCollectionReward
from app.models.enums import RARITY_ORDER, CardSource, NotificationType, Rarity, TransactionType
from app.models.pack import Pack
from app.models.player import Player
from app.models.user import User
from app.schemas.collection import (
    AlbumCollectionDetailOut,
    AlbumCollectionSummaryOut,
    AlbumOverviewOut,
    AlbumPlayerOut,
    CollectionFilterParams,
    SkilledCopyOut,
    UserCardListItem,
)
from app.schemas.pack import CollectionRewardGrantOut
from app.schemas.player import PlayerOut
from app.services import notification_service
from app.services.card_skill_service import require_skill_loss_confirmation
from app.services.player_stats_service import card_rating_bonus
from app.services.wallet_service import credit_coins, lock_user_for_update

OTHER_COLLECTION_ID = -1


async def _duplicate_counts(db: AsyncSession, user_id: int) -> dict[int, int]:
    result = await db.execute(
        select(UserCard.player_id, func.count(UserCard.id))
        .where(UserCard.owner_id == user_id)
        .group_by(UserCard.player_id)
    )
    return {player_id: count for player_id, count in result.all()}


async def _skilled_copies(db: AsyncSession, user_id: int, player_ids: Iterable[int]) -> dict[int, list[SkilledCopyOut]]:
    ids = list(player_ids)
    if not ids:
        return {}
    result = await db.execute(
        select(UserCard)
        .where(UserCard.owner_id == user_id, UserCard.player_id.in_(ids), UserCard.skill_code.is_not(None))
        .order_by(UserCard.skill_level.desc(), UserCard.serial_number)
    )
    by_player: dict[int, list[SkilledCopyOut]] = {}
    for card in result.scalars().all():
        by_player.setdefault(card.player_id, []).append(SkilledCopyOut(
            id=card.id, serial_number=card.serial_number, skill_code=card.skill_code, skill_level=card.skill_level,
        ))
    return by_player


async def personal_squad_card_ids(db: AsyncSession, card_ids: Iterable[int]) -> set[int]:
    """Copies standing in a player-tournament squad — those squads don't set
    a flag on the card (unlike Card Arena / Tactico)."""
    from app.models.personal_squad import PersonalSquadCard

    ids = list(card_ids)
    if not ids:
        return set()
    rows = await db.execute(select(PersonalSquadCard.user_card_id).where(PersonalSquadCard.user_card_id.in_(ids)))
    return set(rows.scalars().all())


async def _owner_personal_squad_ids(db: AsyncSession, user_id: int) -> set[int]:
    from app.models.personal_squad import PersonalSquadCard

    rows = await db.execute(
        select(PersonalSquadCard.user_card_id)
        .join(UserCard, UserCard.id == PersonalSquadCard.user_card_id)
        .where(UserCard.owner_id == user_id)
    )
    return set(rows.scalars().all())


def _stands_alone(card, personal_squad_ids: set[int]) -> bool:
    """A copy listed as its own tile instead of collapsing behind its
    duplicates: it has a skill, stars/Academy progress, stands in a squad or
    is under the owner's «замок» — pickers and quick actions must be able to
    reach exactly that copy, and a squad copy is shown with its lock."""
    return bool(
        card.skill_code or _invested(card) or card.is_in_lineup or card.is_in_tactico_squad
        or card.is_user_locked or card.id in personal_squad_ids
    )


def _pick_representative(current: Optional[UserCard], card: UserCard) -> UserCard:
    """First card in sort order, except that a copy WITHOUT a skill wins over
    a skilled one: the list's quick actions (sell, select-to-sell) act on the
    representative, so they should never silently pick the skilled copy
    while a plain duplicate exists. Skilled copies are listed separately."""
    if current is None:
        return card
    if (current.skill_code or _invested(current)) and not (card.skill_code or _invested(card)):
        return card
    return current


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
    if getattr(filters, "has_skill", None) is True:
        query = query.where(UserCard.skill_code.is_not(None))
    elif getattr(filters, "has_skill", None) is False:
        query = query.where(UserCard.skill_code.is_(None))

    if filters.sort_by == "rating":
        order_col = Player.rating
    elif filters.sort_by == "rarity":
        order_col = Player.rating  # secondary tiebreaker; rarity ordered below in python
    else:
        order_col = UserCard.acquired_at

    query = query.order_by(order_col.desc() if filters.sort_dir == "desc" else order_col.asc())

    # Pagination and totals are computed after collapsing duplicate copies of
    # the same player (below), so the whole filtered set is scanned — but only
    # as LIGHT rows (the few columns the grouping needs, no Player objects);
    # full cards are loaded for the requested page alone (two-phase load).
    light = (await db.execute(query.with_only_columns(
        UserCard.id, UserCard.player_id, UserCard.skill_code, UserCard.stars, UserCard.star_progress,
        UserCard.path_level, UserCard.path_stage, UserCard.prestige, Player.rarity,
        UserCard.is_in_lineup, UserCard.is_in_tactico_squad, UserCard.is_user_locked,
    ))).all()
    all_cards = [
        SimpleNamespace(
            id=r.id, player_id=r.player_id, skill_code=r.skill_code, rarity=r.rarity,
            is_in_lineup=r.is_in_lineup, is_in_tactico_squad=r.is_in_tactico_squad, is_user_locked=r.is_user_locked,
            has_star_investment=(lambda r=r: bool(r.stars or r.star_progress)),
            has_path_progress=(lambda r=r: bool(r.path_level or r.path_stage or r.prestige)),
        )
        for r in light
    ]
    squad_ids = await _owner_personal_squad_ids(db, user_id)

    if filters.sort_by == "rarity":
        all_cards.sort(key=lambda c: RARITY_ORDER[c.rarity], reverse=(filters.sort_dir == "desc"))

    # A user can own several copies of the same player (duplicates); the
    # collection list should show each player once, with duplicate_count
    # conveying how many copies are owned — not one row per physical card.
    # Exception: a copy with a skill, stars / a started «копилка», standing in
    # a squad or under the owner's «замок» is a distinct item of its own
    # (keyed by its card id, see _stands_alone), because every picker built on
    # this list (lineups, tournament squads, trades, sell) must be able to
    # choose exactly that copy — plain duplicates stay collapsed behind one
    # representative.
    representative_by_key: dict[object, UserCard] = {}
    for card in all_cards:
        key = ("own", card.id) if _stands_alone(card, squad_ids) else card.player_id
        representative_by_key[key] = _pick_representative(representative_by_key.get(key), card)
    unique_cards = list(representative_by_key.values())

    total = len(unique_cards)
    page_ids = [c.id for c in unique_cards[params.offset : params.offset + params.page_size]]
    loaded = {
        c.id: c for c in (await db.execute(
            select(UserCard).where(UserCard.id.in_(page_ids)).options(joinedload(UserCard.player))
        )).unique().scalars().all()
    } if page_ids else {}
    page_cards = [loaded[i] for i in page_ids if i in loaded]

    dup_counts = await _duplicate_counts(db, user_id)
    skilled = await _skilled_copies(db, user_id, (c.player_id for c in page_cards))
    in_squad = squad_ids
    items = []
    for card in page_cards:
        item = UserCardListItem.model_validate(card)
        item.duplicate_count = dup_counts.get(card.player_id, 1)
        item.skilled_copies = skilled.get(card.player_id, [])
        item.in_personal_squad = card.id in in_squad
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
    item.skilled_copies = (await _skilled_copies(db, user_id, [card.player_id])).get(card.player_id, [])
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
    if card.is_in_tactico_squad:
        raise ConflictError("Card is used in your Tactico squad")
    if card.is_user_locked:
        raise ConflictError(
            f"«{card.player.display_name}» под замком — сними замок, чтобы продать", details={"reason": "user_locked"},
        )

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


async def sell_cards(
    db: AsyncSession, user: User, user_card_ids: List[int], confirm_last_copy: bool, confirm_skill_loss: bool = False,
) -> dict:
    locked_user = await lock_user_for_update(db, user.id)

    result = await db.execute(
        select(UserCard).where(UserCard.id.in_(user_card_ids)).options(joinedload(UserCard.player))
    )
    cards = result.unique().scalars().all()
    if len(cards) != len(set(user_card_ids)):
        raise NotFoundError("One or more cards not found")

    from app.services.game_config_service import get_config
    from app.services.path_prestige_service import sell_price

    config = await get_config(db)
    total_value = 0
    for card in cards:
        await _assert_sellable(db, user.id, card, confirm_last_copy)
        # «Академия» prestige raises a copy's quick-sell price.
        total_value += sell_price(card, config)
    require_skill_loss_confirmation(list(cards), confirm_skill_loss, "продажа")

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


def _invested(card: UserCard) -> bool:
    """Stars / «копилка» or «Академия» progress — a copy that is not
    interchangeable with its duplicates (listed on its own, never sold as a
    spare)."""
    return card.has_star_investment() or card.has_path_progress()


def _locked(card: UserCard) -> bool:
    """Locked, in a squad or under the owner's own «замок» — never sold as a spare."""
    return not card.can_burn()


async def duplicate_sale_plan(
    db: AsyncSession, user_id: int, include_diamond: bool = False, include_star_material: bool = False,
) -> list[UserCard]:
    """Copies "Продать дубликаты" would sell: for every player owned more than
    once, one copy is always kept (a locked / in-squad / skilled / starred
    copy if there is one, otherwise the best-bonus, lowest-numbered copy),
    and only plain, unlocked, skill-less, star-less spare copies are sold.
    Diamond cards are left alone unless asked (they are diamond-upgrade
    material), and so are the spares of a player whose copy already has
    stars or a started «копилка» (they are star material) unless asked."""
    result = await db.execute(
        select(UserCard).where(UserCard.owner_id == user_id).options(joinedload(UserCard.player))
    )
    by_player: dict[int, list[UserCard]] = {}
    for card in result.unique().scalars().all():
        by_player.setdefault(card.player_id, []).append(card)
    to_sell: list[UserCard] = []
    for copies in by_player.values():
        if len(copies) < 2:
            continue
        protected = [c for c in copies if _locked(c) or c.skill_code or _invested(c)]
        if not protected:
            keeper = sorted(copies, key=lambda c: (-card_rating_bonus(c), c.serial_number or 0))[0]
            protected = [keeper]
        if not include_star_material and any(c.has_star_investment() for c in copies):
            continue
        for card in copies:
            if card in protected or _locked(card) or card.skill_code or _invested(card):
                continue
            if card.player.rarity == Rarity.diamond and not include_diamond:
                continue
            to_sell.append(card)
    return to_sell


async def sell_duplicates(
    db: AsyncSession, user: User, preview: bool, include_diamond: bool = False, include_star_material: bool = False,
) -> dict:
    plan = await duplicate_sale_plan(db, user.id, include_diamond, include_star_material)
    coins = sum(c.player.quick_sell_price for c in plan)
    by_rarity: dict[str, int] = {}
    for card in plan:
        by_rarity[card.player.rarity.value] = by_rarity.get(card.player.rarity.value, 0) + 1
    if preview or not plan:
        return {"sold_count": len(plan), "coins_earned": coins, "by_rarity": by_rarity, "new_balance": user.balance, "preview": True}
    # sell_cards re-checks ownership/locks under the user lock and is atomic.
    result = await sell_cards(db, user, [c.id for c in plan], confirm_last_copy=False)
    return {**result, "by_rarity": by_rarity, "preview": False}


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
        all_owned = cards_result.unique().scalars().all()
        in_squad = await personal_squad_card_ids(db, [c.id for c in all_owned])
        squad_copy: dict[int, UserCard] = {}
        for card in all_owned:
            dup_counts[card.player_id] = dup_counts.get(card.player_id, 0) + 1
            owned_cards[card.player_id] = _pick_representative(owned_cards.get(card.player_id), card)
            if card.is_in_lineup or card.is_in_tactico_squad or card.id in in_squad:
                squad_copy.setdefault(card.player_id, card)
        # The album shows the copy that plays (with its squad lock) when
        # there is one, so it can be opened and upgraded from here.
        owned_cards.update(squad_copy)
    else:
        in_squad = set()
    skilled = await _skilled_copies(db, user_id, owned_cards.keys())

    slots: List[AlbumPlayerOut] = []
    for player in players:
        card = owned_cards.get(player.id)
        card_item = None
        if card is not None:
            card_item = UserCardListItem.model_validate(card)
            card_item.duplicate_count = dup_counts.get(player.id, 1)
            card_item.skilled_copies = skilled.get(player.id, [])
            card_item.in_personal_squad = card.id in in_squad
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


# ---- The owner's «замок» and card filters ----

MAX_LOCK_BATCH = 200


async def set_cards_user_locked(db: AsyncSession, user: User, card_ids: List[int], locked: bool) -> list[int]:
    """Puts (or takes off) the owner's «замок» on several copies at once.
    Under the user row lock, so it serializes with selling."""
    ids = list(dict.fromkeys(card_ids))
    if not ids:
        raise ConflictError("Выбери карточки", details={"reason": "no_cards"})
    if len(ids) > MAX_LOCK_BATCH:
        raise ConflictError(f"За раз можно не больше {MAX_LOCK_BATCH} карточек", details={"reason": "too_many"})
    await lock_user_for_update(db, user.id)
    cards = (
        await db.execute(select(UserCard).where(UserCard.id.in_(ids)).order_by(UserCard.id).with_for_update())
    ).scalars().all()
    if len(cards) != len(ids) or any(c.owner_id != user.id for c in cards):
        raise NotFoundError("Card not found")
    for card in cards:
        card.is_user_locked = locked
    await db.commit()
    return [c.id for c in cards]


async def card_filter_options(db: AsyncSession, user_id: int) -> dict:
    """Countries and clubs present among the owner's cards (for the filter
    pickers), most common first."""
    async def _distinct(column) -> list[str]:
        rows = await db.execute(
            select(column, func.count(UserCard.id))
            .join(UserCard, UserCard.player_id == Player.id)
            .where(UserCard.owner_id == user_id)
            .group_by(column)
            .order_by(func.count(UserCard.id).desc(), column)
        )
        return [value for value, _ in rows.all() if value]

    return {"countries": await _distinct(Player.country), "clubs": await _distinct(Player.club)}


FILTER_KEYS = {"rarity", "country", "club", "position", "sort_by", "has_skill"}


def clean_filter_default(raw: Optional[dict]) -> Optional[dict]:
    """Keeps only the known keys with simple values; empty → None."""
    if not raw:
        return None
    cleaned = {
        k: v for k, v in raw.items()
        if k in FILTER_KEYS and v not in (None, "", []) and isinstance(v, (str, bool))
    }
    if "rarity" in cleaned and cleaned["rarity"] not in {r.value for r in Rarity}:
        cleaned.pop("rarity")
    if "position" in cleaned:
        from app.models.enums import Position
        if cleaned["position"] not in {p.value for p in Position}:
            cleaned.pop("position")
    if "sort_by" in cleaned and cleaned["sort_by"] not in {"acquired_at", "rating", "rarity"}:
        cleaned.pop("sort_by")
    return cleaned or None


async def save_filter_default(db: AsyncSession, user: User, raw: Optional[dict]) -> Optional[dict]:
    user.card_filter_default = clean_filter_default(raw)
    db.add(user)
    await db.commit()
    return user.card_filter_default
