import random
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.card import UserCard
from app.models.enums import RARITY_ORDER, CardSource, Rarity, TransactionType
from app.models.pack import Pack, PackOpening, PackOpeningCard, PackRarityProbability
from app.models.player import Player
from app.models.user import User
from app.schemas.pack import OpenedCardOut, PackOpenResult, PackOut
from app.services.achievement_service import evaluate_and_award
from app.services.card_creation import create_user_card
from app.services.wallet_service import debit_coins, lock_user_for_update


async def _get_pack_or_404(db: AsyncSession, pack_id: int) -> Pack:
    result = await db.execute(
        select(Pack).where(Pack.id == pack_id).options(joinedload(Pack.rarity_probabilities))
    )
    pack = result.unique().scalar_one_or_none()
    if not pack:
        raise NotFoundError("Pack not found")
    return pack


def _assert_pack_available(pack: Pack) -> None:
    if not pack.is_active:
        raise ConflictError("This pack is not currently available")
    now = datetime.now(timezone.utc)
    if pack.available_from and now < pack.available_from:
        raise ConflictError("This pack is not on sale yet")
    if pack.available_until and now > pack.available_until:
        raise ConflictError("This pack sale has ended")


async def _assert_purchase_limit(db: AsyncSession, pack: Pack, user_id: int) -> None:
    if pack.purchase_limit_per_user is None:
        return
    count = (
        await db.execute(
            select(func.count(PackOpening.id)).where(
                PackOpening.pack_id == pack.id, PackOpening.user_id == user_id
            )
        )
    ).scalar_one()
    if count >= pack.purchase_limit_per_user:
        raise ConflictError("Purchase limit reached for this pack")


def roll_rarities(probabilities: list[PackRarityProbability], card_count: int, guaranteed_min_rarity: Optional[Rarity]) -> list[Rarity]:
    rarities = [p.rarity for p in probabilities]
    weights = [float(p.probability) for p in probabilities]
    if not rarities or sum(weights) <= 0:
        rarities, weights = [Rarity.common], [1.0]

    rolled = random.choices(rarities, weights=weights, k=card_count)

    if guaranteed_min_rarity is not None:
        min_order = RARITY_ORDER[guaranteed_min_rarity]
        if not any(RARITY_ORDER[r] >= min_order for r in rolled):
            eligible = [(r, w) for r, w in zip(rarities, weights) if RARITY_ORDER[r] >= min_order]
            if not eligible:
                eligible = [(guaranteed_min_rarity, 1.0)]
            forced_rarity = random.choices([r for r, _ in eligible], weights=[w for _, w in eligible], k=1)[0]
            rolled[-1] = forced_rarity

    return rolled


async def pick_random_player(db: AsyncSession, rarity: Rarity) -> Player:
    result = await db.execute(
        select(Player).where(Player.rarity == rarity, Player.is_active.is_(True)).order_by(func.random()).limit(1)
    )
    player = result.scalar_one_or_none()
    if player is None:
        # Fall back to any active player if this rarity has no active players configured.
        result = await db.execute(select(Player).where(Player.is_active.is_(True)).order_by(func.random()).limit(1))
        player = result.scalar_one_or_none()
    if player is None:
        raise ConflictError("No active players configured; cannot open packs")
    return player


async def _existing_opening_result(db: AsyncSession, user: User, opening: PackOpening) -> PackOpenResult:
    pack = await _get_pack_or_404(db, opening.pack_id)
    result = await db.execute(
        select(PackOpeningCard)
        .where(PackOpeningCard.opening_id == opening.id)
        .options(joinedload(PackOpeningCard.opening))
    )
    opening_cards = result.unique().scalars().all()
    card_ids = [oc.user_card_id for oc in opening_cards]
    cards_result = await db.execute(
        select(UserCard).where(UserCard.id.in_(card_ids)).options(joinedload(UserCard.player))
    )
    cards_by_id = {c.id: c for c in cards_result.unique().scalars().all()}

    dup_counts = await _duplicate_counts_snapshot(db, user.id)
    items = []
    for oc in opening_cards:
        card = cards_by_id[oc.user_card_id]
        items.append(
            OpenedCardOut(
                card=card,
                is_new=oc.is_new_player,
                duplicate_count=dup_counts.get(card.player_id, 1),
            )
        )
    return PackOpenResult(opening_id=opening.id, pack=PackOut.model_validate(pack), cards=items, new_balance=user.balance)


async def _duplicate_counts_snapshot(db: AsyncSession, user_id: int) -> dict[int, int]:
    result = await db.execute(
        select(UserCard.player_id, func.count(UserCard.id)).where(UserCard.owner_id == user_id).group_by(UserCard.player_id)
    )
    return {player_id: count for player_id, count in result.all()}


async def open_pack(db: AsyncSession, user: User, pack_id: int, idempotency_key: Optional[str]) -> PackOpenResult:
    if idempotency_key:
        existing = (
            await db.execute(
                select(PackOpening).where(
                    PackOpening.user_id == user.id, PackOpening.idempotency_key == idempotency_key
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return await _existing_opening_result(db, user, existing)

    pack = await _get_pack_or_404(db, pack_id)
    _assert_pack_available(pack)
    await _assert_purchase_limit(db, pack, user.id)

    locked_user = await lock_user_for_update(db, user.id)

    await debit_coins(
        db,
        locked_user,
        pack.price,
        TransactionType.pack_purchase,
        f"Открытие пака «{pack.name}»",
        related_object_type="pack",
        related_object_id=pack.id,
    )

    opening = PackOpening(
        user_id=locked_user.id,
        pack_id=pack.id,
        price_paid=pack.price,
        idempotency_key=idempotency_key,
        created_at=datetime.now(timezone.utc),
    )
    db.add(opening)
    await db.flush()

    dup_counts = await _duplicate_counts_snapshot(db, locked_user.id)
    seen_this_opening: set[int] = set()
    rolled_rarities = roll_rarities(pack.rarity_probabilities, pack.card_count, pack.guaranteed_min_rarity)

    opened_items: list[OpenedCardOut] = []
    for rarity in rolled_rarities:
        player = await pick_random_player(db, rarity)
        is_new = dup_counts.get(player.id, 0) == 0 and player.id not in seen_this_opening
        seen_this_opening.add(player.id)
        dup_counts[player.id] = dup_counts.get(player.id, 0) + 1

        user_card = await create_user_card(db, locked_user.id, player.id, CardSource.pack, opening.id)

        db.add(PackOpeningCard(opening_id=opening.id, user_card_id=user_card.id, is_new_player=is_new))
        user_card.player = player
        opened_items.append(
            OpenedCardOut(card=user_card, is_new=is_new, duplicate_count=dup_counts[player.id])
        )

    total_openings = (
        await db.execute(select(func.count(PackOpening.id)).where(PackOpening.user_id == locked_user.id))
    ).scalar_one()
    await evaluate_and_award(db, locked_user, "packs_opened", total_openings)
    await evaluate_and_award(db, locked_user, "unique_players", len(dup_counts))

    try:
        await db.commit()
    except IntegrityError:
        # Two concurrent requests raced with the same idempotency key (e.g. a
        # duplicated client-side submit): the loser rolls back and returns the
        # winner's already-committed result instead of erroring or double-charging.
        await db.rollback()
        if idempotency_key:
            existing = (
                await db.execute(
                    select(PackOpening).where(
                        PackOpening.user_id == user.id, PackOpening.idempotency_key == idempotency_key
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return await _existing_opening_result(db, user, existing)
        raise
    await db.refresh(locked_user)

    return PackOpenResult(
        opening_id=opening.id,
        pack=PackOut.model_validate(pack),
        cards=opened_items,
        new_balance=locked_user.balance,
    )


async def list_available_packs(db: AsyncSession, user_id: Optional[int] = None) -> list[PackOut]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Pack).where(Pack.is_active.is_(True)).options(joinedload(Pack.rarity_probabilities)).order_by(Pack.sort_order)
    )
    packs = result.unique().scalars().all()
    out = []
    for pack in packs:
        purchase_count = 0
        if user_id is not None and pack.purchase_limit_per_user is not None:
            purchase_count = (
                await db.execute(
                    select(func.count(PackOpening.id)).where(
                        PackOpening.pack_id == pack.id, PackOpening.user_id == user_id
                    )
                )
            ).scalar_one()
        is_available_now = True
        if pack.available_from and now < pack.available_from:
            is_available_now = False
        if pack.available_until and now > pack.available_until:
            is_available_now = False
        item = PackOut.model_validate(pack)
        item.user_purchase_count = purchase_count
        item.is_available_now = is_available_now
        out.append(item)
    return out
