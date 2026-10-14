"""«Звёзды карточек»: duplicates of the same player make ONE owned copy
stronger.

Rules (every number lives on GameConfig, editable from the admin panel):
  * A copy banks duplicates of its own player in `star_progress` («копилка»)
    — any amount, any time. Star N needs card_star_dupes_per_level[rarity][N-1]
    banked duplicates and costs card_star_coin_cost[rarity][N-1] coins, charged
    when the star is claimed; extra duplicates roll over to the next star.
  * Stars are claimed automatically while feeding if the coins are there;
    otherwise the progress stays banked and POST .../stars/claim takes it later.
  * Each star adds card_star_rating_per_star rating (total capped by
    card_star_bonus_cap, the card itself by 99). The bonus is written to
    UserCard.star_rating_bonus when a star is claimed and never lowered by a
    later retune, so it behaves exactly like diamond_rating_bonus everywhere
    (player_stats_service.card_rating_bonus).
  * Diamond cards never take stars — they have their own upgrade.
  * card_stars_enabled=False blocks feeding and claiming; stars already
    earned keep working (same as card skills).

Atomicity: the owner row is locked first (wallet_service.lock_user_for_update
— which also serializes every star operation of one user), then the target
and the material cards FOR UPDATE; materials are deleted, coins debited and a
CardStarLedger row written in one commit. A retried request with the same
idempotency_key replays instead of charging twice (unique constraint).
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, InsufficientBalanceError, NotFoundError
from app.models.card import CardStarLedger, UserCard
from app.models.enums import Rarity, TransactionType
from app.models.game_config import GameConfig
from app.models.personal_squad import PersonalSquadCard
from app.models.user import User
from app.schemas.card_star import (
    CardStarFeedRequest, CardStarOperationOut, CardStarStateOut, StarMaterialOut,
)
from app.services.card_skill_service import require_skill_loss_confirmation
from app.services.game_config_service import get_config
from app.services.player_stats_service import card_rating_bonus
from app.services.wallet_service import debit_coins, lock_user_for_update

MAX_RATING = 99


def star_levels(config: GameConfig, rarity: Rarity) -> tuple[list[int], list[int]]:
    """(duplicates per star, coins per star) for this rarity, cut to
    card_stars_max. Empty for diamond and for any rarity the admin left out."""
    if rarity == Rarity.diamond:
        return [], []
    thresholds = list((config.card_star_dupes_per_level or {}).get(rarity.value) or [])
    coins = list((config.card_star_coin_cost or {}).get(rarity.value) or [])
    count = max(0, min(int(config.card_stars_max), len(thresholds)))
    return (
        [max(1, int(t)) for t in thresholds[:count]],
        [max(0, int(coins[i])) if i < len(coins) else 0 for i in range(count)],
    )


def star_rating_bonus_for(config: GameConfig, stars: int) -> int:
    return max(0, min(stars * int(config.card_star_rating_per_star), int(config.card_star_bonus_cap)))


def dupes_to_max(card: UserCard, thresholds: list[int]) -> int:
    return max(0, sum(thresholds[card.stars:]) - card.star_progress)


def _target_block_reason(card: UserCard, config: GameConfig, thresholds: list[int]) -> Optional[str]:
    if not config.card_stars_enabled:
        return "Звёзды карточек временно отключены"
    if card.player.rarity == Rarity.diamond:
        return "У бриллиантовых карточек своя прокачка — звёзды им не нужны"
    if not thresholds:
        return "Для этой редкости звёзды не настроены"
    if card.is_locked_by_admin:
        return "Карточка заблокирована администратором"
    if card.is_locked_in_trade:
        return "Карточка участвует в активном обмене"
    if card.stars >= len(thresholds):
        return "У карточки уже максимум звёзд"
    return None


async def _squad_card_ids(db: AsyncSession, card_ids: list[int]) -> set[int]:
    """Copies standing in a player-tournament squad (those squads don't set a
    lock flag on the card, but burning one would silently empty a slot)."""
    if not card_ids:
        return set()
    result = await db.execute(select(PersonalSquadCard.user_card_id).where(PersonalSquadCard.user_card_id.in_(card_ids)))
    return set(result.scalars().all())


def _material_block_reason(card: UserCard, target: UserCard, in_squad: set[int]) -> Optional[str]:
    if card.id == target.id:
        return "Карточку нельзя вложить саму в себя"
    if card.owner_id != target.owner_id:
        return "Карточка не найдена"
    if card.player_id != target.player_id:
        return "Вкладывать можно только дубли этого же игрока"
    if card.is_locked() or card.id in in_squad:
        return "Карточка в составе, в обмене или заблокирована"
    if card.has_star_investment():
        return "У этой копии свои звёзды или копилка — её нельзя вложить"
    return None


async def _free_duplicates(db: AsyncSession, target: UserCard, lock: bool) -> list[UserCard]:
    query = (
        select(UserCard)
        .where(UserCard.owner_id == target.owner_id, UserCard.player_id == target.player_id, UserCard.id != target.id)
        .order_by(UserCard.id)
    )
    if lock:
        query = query.with_for_update(of=UserCard).execution_options(populate_existing=True)
    copies = list((await db.execute(query)).scalars().all())
    in_squad = await _squad_card_ids(db, [c.id for c in copies])
    free = [c for c in copies if _material_block_reason(c, target, in_squad) is None]
    # Skill-less copies first, then the highest serial (low numbers are the
    # ones collectors keep).
    return sorted(free, key=lambda c: (c.skill_code is not None, -(c.serial_number or 0)))


async def _state(db: AsyncSession, card: UserCard, config: GameConfig) -> CardStarStateOut:
    thresholds, coins = star_levels(config, card.player.rarity)
    base = card.player.rating
    now = min(MAX_RATING, base + card_rating_bonus(card))
    has_next = card.stars < len(thresholds)
    after_next = None
    if has_next:
        next_bonus = max(card.star_rating_bonus, star_rating_bonus_for(config, card.stars + 1))
        after_next = min(MAX_RATING, base + (card.diamond_rating_bonus or 0) + next_bonus)
    free = await _free_duplicates(db, card, lock=False)
    return CardStarStateOut(
        card_id=card.id, player_id=card.player_id, rarity=card.player.rarity.value,
        enabled=bool(config.card_stars_enabled), block_reason=_target_block_reason(card, config, thresholds),
        stars=card.stars, max_stars=len(thresholds), progress=card.star_progress,
        thresholds=thresholds, coin_costs=coins,
        next_threshold=thresholds[card.stars] if has_next else None,
        next_coin_cost=coins[card.stars] if has_next else None,
        claimable=has_next and card.star_progress >= thresholds[card.stars],
        dupes_to_max=dupes_to_max(card, thresholds),
        rating_base=base, rating_now=now, rating_bonus=card.star_rating_bonus, rating_after_next_star=after_next,
        free_duplicates=[
            StarMaterialOut(id=c.id, serial_number=c.serial_number, skill_code=c.skill_code, skill_level=c.skill_level)
            for c in free
        ],
    )


async def _load_card(db: AsyncSession, user_id: int, card_id: int, lock: bool) -> UserCard:
    query = select(UserCard).where(UserCard.id == card_id).options(joinedload(UserCard.player))
    if lock:
        query = query.with_for_update(of=UserCard).execution_options(populate_existing=True)
    card = (await db.execute(query)).scalar_one_or_none()
    if card is None or card.owner_id != user_id:
        raise NotFoundError("Card not found")
    return card


async def get_state(db: AsyncSession, user: User, card_id: int) -> CardStarStateOut:
    card = await _load_card(db, user.id, card_id, lock=False)
    return await _state(db, card, await get_config(db))


async def _claim_ready_stars(
    db: AsyncSession, locked_user: User, card: UserCard, config: GameConfig, thresholds: list[int], coins: list[int],
) -> tuple[int, int]:
    """Claims every star the banked progress covers while the coins last.
    Returns (stars gained, coins spent)."""
    gained = spent = 0
    while card.stars < len(thresholds) and card.star_progress >= thresholds[card.stars]:
        cost = coins[card.stars]
        if locked_user.balance < cost:
            break
        if cost > 0:
            await debit_coins(
                db, locked_user, cost, TransactionType.card_star_upgrade,
                f"Звезда {card.stars + 1} для «{card.player.display_name}» #{card.serial_number}",
                related_object_type="user_card", related_object_id=card.id,
            )
        card.star_progress -= thresholds[card.stars]
        card.stars += 1
        card.star_rating_bonus = max(card.star_rating_bonus, star_rating_bonus_for(config, card.stars))
        gained += 1
        spent += cost
    return gained, spent


async def _ledger_by_key(db: AsyncSession, user_id: int, key: Optional[str]) -> Optional[CardStarLedger]:
    if not key:
        return None
    result = await db.execute(
        select(CardStarLedger).where(CardStarLedger.user_id == user_id, CardStarLedger.idempotency_key == key)
    )
    return result.scalar_one_or_none()


async def _replay(db: AsyncSession, user: User, entry: CardStarLedger, card_id: int) -> CardStarOperationOut:
    if entry.user_card_id != card_id:
        raise ConflictError("Этот ключ операции уже использован для другой карточки", details={"reason": "key_reused"})
    card = await _load_card(db, user.id, card_id, lock=False)
    await db.refresh(user)
    return CardStarOperationOut(
        kind=entry.kind, cards_consumed=entry.cards_consumed, stars_gained=entry.stars_after - entry.stars_before,
        coins_spent=entry.coins_spent, new_balance=user.balance, replayed=True,
        state=await _state(db, card, await get_config(db)),
    )


async def _commit_or_replay(db: AsyncSession, user: User, key: Optional[str], card_id: int) -> Optional[CardStarOperationOut]:
    try:
        await db.commit()
        return None
    except IntegrityError:
        await db.rollback()
        existing = await _ledger_by_key(db, user.id, key)
        if existing is not None:
            return await _replay(db, user, existing, card_id)
        raise


async def feed(db: AsyncSession, user: User, card_id: int, request: CardStarFeedRequest) -> CardStarOperationOut:
    existing = await _ledger_by_key(db, user.id, request.idempotency_key)
    if existing is not None:
        return await _replay(db, user, existing, card_id)
    if not request.all_free and not request.material_card_ids:
        raise ConflictError("Выбери дубли для вложения", details={"reason": "no_materials"})
    if len(set(request.material_card_ids)) != len(request.material_card_ids):
        raise ConflictError("Одна и та же карточка указана дважды", details={"reason": "duplicate_ids"})

    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    card = await _load_card(db, locked_user.id, card_id, lock=True)
    thresholds, coins = star_levels(config, card.player.rarity)
    block = _target_block_reason(card, config, thresholds)
    if block is not None:
        raise ConflictError(block, details={"reason": "card_blocked"})

    if request.all_free:
        materials = [c for c in await _free_duplicates(db, card, lock=True) if c.skill_code is None]
    else:
        ids = request.material_card_ids
        locked = (
            await db.execute(
                select(UserCard).where(UserCard.id.in_(ids)).order_by(UserCard.id)
                .with_for_update(of=UserCard).execution_options(populate_existing=True)
            )
        ).scalars().all()
        by_id = {c.id: c for c in locked}
        if len(by_id) != len(ids) or any(c.owner_id != locked_user.id for c in by_id.values()):
            raise NotFoundError("Card not found")
        in_squad = await _squad_card_ids(db, ids)
        materials = [by_id[i] for i in ids]
        for material in materials:
            reason = _material_block_reason(material, card, in_squad)
            if reason is not None:
                raise ConflictError(reason, details={"reason": "material_blocked", "card_id": material.id})
        require_skill_loss_confirmation(materials, request.confirm_skill_loss, "вложение в звёзды")

    need = dupes_to_max(card, thresholds)
    consumed = materials[:need]
    if not consumed:
        raise ConflictError("Нет свободных дублей этого игрока без навыков", details={"reason": "no_materials"})

    stars_before, progress_before = card.stars, card.star_progress
    for material in consumed:
        await db.delete(material)
    card.star_progress += len(consumed)
    gained, spent = await _claim_ready_stars(db, locked_user, card, config, thresholds, coins)
    db.add(card)
    db.add(CardStarLedger(
        user_id=locked_user.id, user_card_id=card.id, kind="feed", cards_consumed=len(consumed),
        consumed_card_ids=[c.id for c in consumed], stars_before=stars_before, stars_after=card.stars,
        progress_before=progress_before, progress_after=card.star_progress, coins_spent=spent,
        rating_bonus_after=card.star_rating_bonus, idempotency_key=request.idempotency_key,
    ))
    replay = await _commit_or_replay(db, locked_user, request.idempotency_key, card_id)
    if replay is not None:
        return replay
    return CardStarOperationOut(
        kind="feed", cards_consumed=len(consumed), stars_gained=gained, coins_spent=spent,
        new_balance=locked_user.balance, state=await _state(db, card, config),
    )


async def claim(db: AsyncSession, user: User, card_id: int, idempotency_key: Optional[str]) -> CardStarOperationOut:
    existing = await _ledger_by_key(db, user.id, idempotency_key)
    if existing is not None:
        return await _replay(db, user, existing, card_id)

    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    card = await _load_card(db, locked_user.id, card_id, lock=True)
    thresholds, coins = star_levels(config, card.player.rarity)
    block = _target_block_reason(card, config, thresholds)
    if block is not None:
        raise ConflictError(block, details={"reason": "card_blocked"})
    if card.star_progress < thresholds[card.stars]:
        raise ConflictError(
            f"Для звезды нужно ещё {thresholds[card.stars] - card.star_progress} дублей",
            details={"reason": "not_enough_duplicates"},
        )
    if locked_user.balance < coins[card.stars]:
        raise InsufficientBalanceError(
            "Недостаточно монет для звезды",
            details={"reason": "insufficient_coins", "required": coins[card.stars], "available": locked_user.balance},
        )

    stars_before, progress_before = card.stars, card.star_progress
    gained, spent = await _claim_ready_stars(db, locked_user, card, config, thresholds, coins)
    db.add(card)
    db.add(CardStarLedger(
        user_id=locked_user.id, user_card_id=card.id, kind="claim", cards_consumed=0, consumed_card_ids=[],
        stars_before=stars_before, stars_after=card.stars, progress_before=progress_before,
        progress_after=card.star_progress, coins_spent=spent, rating_bonus_after=card.star_rating_bonus,
        idempotency_key=idempotency_key,
    ))
    replay = await _commit_or_replay(db, locked_user, idempotency_key, card_id)
    if replay is not None:
        return replay
    return CardStarOperationOut(
        kind="claim", cards_consumed=0, stars_gained=gained, coins_spent=spent,
        new_balance=locked_user.balance, state=await _state(db, card, config),
    )
