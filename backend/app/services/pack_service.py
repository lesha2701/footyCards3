import random
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.card import UserCard
from app.models.card_collection import CardCollection
from app.models.enums import RARITY_ORDER, CardSource, NotificationType, Rarity, TransactionType
from app.models.pack import Pack, PackOpening, PackOpeningCard, PackRarityProbability
from app.models.player import Player
from app.models.user import User
from app.schemas.pack import OpenedCardOut, PackOpenResult, PackOut
from app.services import collection_service, notification_service, task_service
from app.services.card_creation import create_user_card
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update


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
    if pack.stars_price is not None:
        raise ConflictError("This pack can only be purchased with Telegram Stars")
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


def _collection_active_filter():
    return or_(Player.collection_id.is_(None), CardCollection.is_active.is_(True))


async def pick_random_player(db: AsyncSession, rarity: Rarity) -> Player:
    result = await db.execute(
        select(Player)
        .outerjoin(CardCollection, Player.collection_id == CardCollection.id)
        .where(
            Player.rarity == rarity, Player.is_active.is_(True), Player.is_pack_droppable.is_(True),
            _collection_active_filter(),
        )
        .order_by(func.random())
        .limit(1)
    )
    player = result.scalar_one_or_none()
    if player is None:
        # Fall back to any active, pack-droppable player (in an active collection) if this rarity has none configured.
        result = await db.execute(
            select(Player)
            .outerjoin(CardCollection, Player.collection_id == CardCollection.id)
            .where(Player.is_active.is_(True), Player.is_pack_droppable.is_(True), _collection_active_filter())
            .order_by(func.random())
            .limit(1)
        )
        player = result.scalar_one_or_none()
    if player is None:
        raise ConflictError("No active players configured; cannot open packs")
    return player


async def get_opening_result(db: AsyncSession, user: User, opening: PackOpening) -> PackOpenResult:
    pack = await _get_pack_or_404(db, opening.pack_id)
    result = await db.execute(
        select(PackOpeningCard)
        .where(PackOpeningCard.opening_id == opening.id)
        .options(joinedload(PackOpeningCard.opening))
        .order_by(PackOpeningCard.id)
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
    items.sort(key=lambda item: RARITY_ORDER[item.card.player.rarity])
    return PackOpenResult(opening_id=opening.id, pack=PackOut.model_validate(pack), cards=items, new_balance=user.balance)


async def _duplicate_counts_snapshot(db: AsyncSession, user_id: int) -> dict[int, int]:
    result = await db.execute(
        select(UserCard.player_id, func.count(UserCard.id)).where(UserCard.owner_id == user_id).group_by(UserCard.player_id)
    )
    return {player_id: count for player_id, count in result.all()}


async def roll_and_create_cards(
    db: AsyncSession,
    user: User,
    pack: Pack,
    opening: PackOpening,
    dup_counts: dict[int, int],
    source: CardSource,
) -> list[OpenedCardOut]:
    seen_this_opening: set[int] = set()
    rolled_rarities = roll_rarities(pack.rarity_probabilities, pack.card_count, pack.guaranteed_min_rarity)

    opened_items: list[OpenedCardOut] = []
    for rarity in rolled_rarities:
        player = await pick_random_player(db, rarity)
        is_new = dup_counts.get(player.id, 0) == 0 and player.id not in seen_this_opening
        seen_this_opening.add(player.id)
        dup_counts[player.id] = dup_counts.get(player.id, 0) + 1

        user_card = await create_user_card(db, user.id, player.id, source, opening.id)

        db.add(PackOpeningCard(opening_id=opening.id, user_card_id=user_card.id, is_new_player=is_new))
        user_card.player = player
        opened_items.append(
            OpenedCardOut(card=user_card, is_new=is_new, duplicate_count=dup_counts[player.id])
        )

    opened_items.sort(key=lambda item: RARITY_ORDER[item.card.player.rarity])
    return opened_items


async def track_pack_opened_tasks(db: AsyncSession, user: User, dup_counts: dict[int, int]) -> None:
    total_openings = (
        await db.execute(select(func.count(PackOpening.id)).where(PackOpening.user_id == user.id))
    ).scalar_one()
    await task_service.evaluate_metric_progress(db, user, "packs_opened", total_openings)
    await task_service.evaluate_metric_progress(db, user, "unique_players", len(dup_counts))


async def _credit_referral_bonus(db: AsyncSession, locked_user: User, locked_referrer: User) -> int:
    """Pure crediting — both users must already be row-locked by the
    caller, in whatever order it arranged (this function takes no locks
    itself). Shared by every pack-granting path's referral check. Returns
    the referred user's own bonus amount, for surfacing in the response."""
    config = await get_config(db)
    locked_user.referral_reward_granted = True
    db.add(locked_user)

    locked_referrer.referral_count += 1
    db.add(locked_referrer)
    await task_service.evaluate_metric_progress(db, locked_referrer, "referrals_count", locked_referrer.referral_count)

    await credit_coins(
        db, locked_user, config.referral_referred_reward, TransactionType.referral_reward,
        "Бонус за переход по реферальной ссылке",
        related_object_type="user", related_object_id=locked_referrer.id,
    )
    await credit_coins(
        db, locked_referrer, config.referral_referrer_reward, TransactionType.referral_reward,
        f"Награда за приглашение друга: {locked_user.full_display_name()}",
        related_object_type="user", related_object_id=locked_user.id,
    )
    await notification_service.notify(
        db, locked_referrer.id, NotificationType.referral_joined,
        "🤝 Новый реферал!",
        f"{locked_user.full_display_name()} присоединился по твоей ссылке и открыл первый пак — "
        f"тебе начислено {config.referral_referrer_reward} монет!",
    )
    return config.referral_referred_reward


async def maybe_grant_referral_bonus_for_locked_user(db: AsyncSession, locked_user: User) -> Optional[int]:
    """Call after ANY pack grant (bonus/task/league/wheel — not just a real
    purchase) once `locked_user` is already row-locked, to credit their
    referrer the first time they ever open a pack. Gated on
    referral_reward_granted (not a purchase count or "was this pack paid"
    check), so it fires exactly once per referred user regardless of which
    kind of pack triggers it, and self-heals anyone previously stuck behind
    a narrower check.

    Unlike open_pack's own inline version, this locks the referrer *after*
    `locked_user` is already locked by the caller (every grant_bonus_pack_
    opening call site locks its own user before calling in), so it can't
    pre-sort the pair the way open_pack/claim_free_pack do — a genuine but
    narrow deadlock risk (only if the referrer is *simultaneously* locking
    themselves-then-this-same-referred-user in the opposite order, e.g. a
    trade between the two of them racing this exact instant). Postgres
    detects and aborts one side of a real deadlock rather than corrupting
    anything, and the caller can simply retry — an acceptable trade against
    threading a fully sorted two-user lock through every one of grant_
    bonus_pack_opening's several unrelated callers.
    """
    if locked_user.referred_by_id is None or locked_user.referral_reward_granted:
        return None
    referrer = await lock_user_for_update(db, locked_user.referred_by_id)
    return await _credit_referral_bonus(db, locked_user, referrer)


async def grant_bonus_pack_opening(
    db: AsyncSession, user: User, pack_id: int, idempotency_prefix: str, source: CardSource = CardSource.task
) -> Optional[PackOpenResult]:
    """Server-initiated pack grant with no payment or purchase-limit checks —
    shared by task rewards, collection-completion rewards, league-tier
    rewards, and wheel-of-fortune bonus packs. Precondition: `user` must
    already be a row-locked User (this function does not lock it itself)."""
    result = await db.execute(
        select(Pack).where(Pack.id == pack_id).options(joinedload(Pack.rarity_probabilities))
    )
    pack = result.unique().scalar_one_or_none()
    if not pack:
        return None

    opening = PackOpening(
        user_id=user.id, pack_id=pack.id, price_paid=0,
        idempotency_key=f"{idempotency_prefix}-{datetime.now(timezone.utc).timestamp()}",
        created_at=datetime.now(timezone.utc),
    )
    db.add(opening)
    await db.flush()

    dup_counts = await _duplicate_counts_snapshot(db, user.id)
    opened_items = await roll_and_create_cards(db, user, pack, opening, dup_counts, source)
    referral_bonus_coins = await maybe_grant_referral_bonus_for_locked_user(db, user)

    return PackOpenResult(
        opening_id=opening.id, pack=PackOut.model_validate(pack), cards=opened_items, new_balance=user.balance,
        referral_bonus_coins=referral_bonus_coins,
    )


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
            return await get_opening_result(db, user, existing)

    pack = await _get_pack_or_404(db, pack_id)
    _assert_pack_available(pack)
    await _assert_purchase_limit(db, pack, user.id)

    # Lock the buyer and (if a referral bonus might still be owed) their
    # referrer together, in ascending-id order — the same canonical
    # ordering trade_service.accept_offer / tactico_service / penalty_match
    # _service use whenever two user rows need locking. Always locking the
    # buyer first (regardless of id) previously caused real deadlocks: e.g.
    # buyer A (referred by R) opening a pack locks A then R, while R
    # concurrently doing anything that locks R then A (a trade with A,
    # A opening a pack that also references R, etc.) locks in the opposite
    # order. `referred_by_id` is immutable once set and `referral_reward_
    # granted` only ever flips False->True, so this pre-check on the
    # possibly-stale `user` argument can only under-predict (harmless —
    # falls back to locking the referrer separately below, exactly like
    # before) never over-predict skipping a still-owed bonus.
    pending_referrer_id = (
        user.referred_by_id if user.referred_by_id is not None and not user.referral_reward_granted else None
    )
    if pending_referrer_id is not None:
        first_id, second_id = sorted([user.id, pending_referrer_id])
        first_locked = await lock_user_for_update(db, first_id)
        second_locked = await lock_user_for_update(db, second_id)
        locked_user = first_locked if first_locked.id == user.id else second_locked
        pre_locked_referrer: Optional[User] = first_locked if first_locked.id == pending_referrer_id else second_locked
    else:
        locked_user = await lock_user_for_update(db, user.id)
        pre_locked_referrer = None

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
    opened_items = await roll_and_create_cards(db, locked_user, pack, opening, dup_counts, CardSource.pack)
    await track_pack_opened_tasks(db, locked_user, dup_counts)
    collection_rewards = await collection_service.grant_collection_rewards_for_new_cards(
        db, locked_user, [item.card.player.id for item in opened_items]
    )

    referral_bonus_coins: Optional[int] = None
    if locked_user.referred_by_id is not None and not locked_user.referral_reward_granted:
        # Fires exactly once per referred user, on whichever pack (paid or
        # free) they open first — `referral_reward_granted` is the gate, not
        # a count of past openings, so it self-heals for anyone who was
        # previously stuck behind the old paid-only/count==1 check.
        #
        # Should always be pre-locked via the sorted (buyer, referrer) pass
        # above — the fallback only matters if the pre-check's possibly-
        # stale `user` argument somehow under-predicted (see comment above).
        referrer = pre_locked_referrer or await lock_user_for_update(db, locked_user.referred_by_id)
        referral_bonus_coins = await _credit_referral_bonus(db, locked_user, referrer)

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
                return await get_opening_result(db, user, existing)
        raise
    await db.refresh(locked_user)

    return PackOpenResult(
        opening_id=opening.id,
        pack=PackOut.model_validate(pack),
        cards=opened_items,
        new_balance=locked_user.balance,
        referral_bonus_coins=referral_bonus_coins,
        collection_rewards=collection_rewards,
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
