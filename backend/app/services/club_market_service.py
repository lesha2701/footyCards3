"""«Лишние карты» клуба: club pack cards that sit in none of the club's five
lineup templates can be

- sold into the club budget for `Player.quick_sell_price` ×
  `club_card_sell_pct` % (the same per-player price admins already tune for
  personal quick-sell), or
- exchanged, `club_card_exchange_count` of one rarity for one random club
  card of the next rarity (common → rare → epic → legendary).

Cards in any lineup template are protected. The club's lineup rows are
locked first, so a sale can't race a captain putting the same card into a
lineup (set_club_lineup locks the template row it edits). Bench cards do
stand in for suspended starters in tournaments — the UI says so; nothing
here forces a minimum bench."""
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.club import Club, ClubMember
from app.models.club_card import ClubCard
from app.models.club_lineup import ClubLineup, ClubLineupCard
from app.models.enums import ClubBudgetTransactionType, ClubCardSource, Rarity
from app.models.game_config import GameConfig
from app.models.player import Player
from app.models.user import User
from app.schemas.club_market import (
    ClubSurplusOut,
    SurplusCardOut,
    SurplusExchangeOptionOut,
    SurplusExchangeOut,
    SurplusSellOut,
)
from app.schemas.club_squad import ClubCardOut
from app.schemas.player import PlayerOut
from app.services.club_budget_service import credit_club_budget
from app.services.club_card_service import create_club_card
from app.services.game_config_service import get_config
from app.services.pack_service import pick_random_player

NEXT_RARITY = {Rarity.common: Rarity.rare, Rarity.rare: Rarity.epic, Rarity.epic: Rarity.legendary}


def sell_value(player: Player, config: GameConfig) -> int:
    return max(0, int(player.quick_sell_price or 0) * config.club_card_sell_pct // 100)


async def _membership(db: AsyncSession, user_id: int) -> ClubMember:
    membership = (await db.execute(select(ClubMember).where(ClubMember.user_id == user_id))).scalar_one_or_none()
    if membership is None:
        raise NotFoundError("Ты не состоишь в клубе")
    return membership


def _can_manage(membership: ClubMember, club: Club) -> bool:
    from app.services.club_service import can_spend_budget

    return can_spend_budget(membership, club)


async def protected_card_ids(db: AsyncSession, club_id: int) -> set[int]:
    rows = await db.execute(
        select(ClubLineupCard.club_card_id)
        .join(ClubLineup, ClubLineup.id == ClubLineupCard.club_lineup_id)
        .where(ClubLineup.club_id == club_id)
    )
    return set(rows.scalars())


async def get_surplus(db: AsyncSession, user: User) -> ClubSurplusOut:
    membership = await _membership(db, user.id)
    club = await db.get(Club, membership.club_id)
    config = await get_config(db)
    protected = await protected_card_ids(db, club.id)
    cards = (await db.execute(
        select(ClubCard).where(ClubCard.club_id == club.id).order_by(ClubCard.acquired_at)
    )).scalars().all()

    out: list[SurplusCardOut] = []
    free_by_rarity: dict[Rarity, int] = {}
    for c in cards:
        is_protected = c.id in protected
        if not is_protected:
            free_by_rarity[c.player.rarity] = free_by_rarity.get(c.player.rarity, 0) + 1
        out.append(SurplusCardOut(
            card=ClubCardOut(
                id=c.id, serial_number=c.serial_number, player=PlayerOut.model_validate(c.player),
                acquired_at=c.acquired_at, is_in_lineup=is_protected,
            ),
            protected=is_protected, sell_value=sell_value(c.player, config),
        ))
    # Protected (squad) cards last, then the most valuable first.
    out.sort(key=lambda s: (s.protected, -s.sell_value))
    return ClubSurplusOut(
        enabled=config.club_card_market_enabled, can_manage=_can_manage(membership, club), budget=club.budget,
        sell_pct=config.club_card_sell_pct, exchange_count=config.club_card_exchange_count,
        cards=out,
        exchange_options=[
            SurplusExchangeOptionOut(rarity=r, target_rarity=t, available=free_by_rarity.get(r, 0))
            for r, t in NEXT_RARITY.items()
        ],
    )


async def _lock_for_change(db: AsyncSession, user: User, card_ids: list[int]) -> tuple[Club, list[ClubCard], GameConfig]:
    config = await get_config(db)
    if not config.club_card_market_enabled:
        raise ConflictError("Продажа и обмен клубных карт сейчас недоступны")
    membership = await _membership(db, user.id)
    from app.services.club_service import require_budget_spender

    require_budget_spender(membership, await db.get(Club, membership.club_id))
    if len(set(card_ids)) != len(card_ids):
        raise ConflictError("Карта указана дважды")
    club = (await db.execute(
        select(Club).where(Club.id == membership.club_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    # Serializes with set_club_lineup (it locks the template row it edits).
    await db.execute(select(ClubLineup.id).where(ClubLineup.club_id == club.id).with_for_update())
    cards = (await db.execute(
        select(ClubCard).where(ClubCard.id.in_(card_ids), ClubCard.club_id == club.id)
    )).scalars().all()
    if len(cards) != len(card_ids):
        raise NotFoundError("Карта не найдена в клубе")
    if await protected_card_ids(db, club.id) & set(card_ids):
        raise ConflictError("Карту из состава нельзя продать или обменять — сначала убери её из всех составов")
    return club, list(cards), config


async def sell_cards(db: AsyncSession, user: User, card_ids: list[int]) -> SurplusSellOut:
    club, cards, config = await _lock_for_change(db, user, card_ids)
    coins = sum(sell_value(c.player, config) for c in cards)
    names = ", ".join(c.player.display_name for c in cards[:3]) + (f" и ещё {len(cards) - 3}" if len(cards) > 3 else "")
    await credit_club_budget(
        db, club, coins, ClubBudgetTransactionType.card_sale, f"Продажа карт: {names}",
        related_object_type="club_card", actor_user_id=user.id,
    )
    await db.execute(delete(ClubCard).where(ClubCard.id.in_(card_ids)))
    await db.commit()
    return SurplusSellOut(sold=len(cards), coins=coins, budget=club.budget)


async def exchange_cards(db: AsyncSession, user: User, card_ids: list[int]) -> SurplusExchangeOut:
    club, cards, config = await _lock_for_change(db, user, card_ids)
    if len(cards) != config.club_card_exchange_count:
        raise ConflictError(f"Для обмена нужно ровно {config.club_card_exchange_count} карт")
    rarities = {c.player.rarity for c in cards}
    if len(rarities) != 1:
        raise ConflictError("Все карты для обмена должны быть одной редкости")
    target = NEXT_RARITY.get(rarities.pop())
    if target is None:
        raise ConflictError("Карты этой редкости не обмениваются")
    # pick_random_player falls back to any rarity when the target one is empty —
    # an exchange must never hand back a lower card, so refuse instead.
    player = await pick_random_player(db, target)
    if player is None or player.rarity != target:
        raise ConflictError("Сейчас нет карт нужной редкости для обмена")
    await db.execute(delete(ClubCard).where(ClubCard.id.in_(card_ids)))
    card = await create_club_card(db, club.id, player.id, ClubCardSource.exchange)
    await db.commit()
    await db.refresh(card)
    return SurplusExchangeOut(
        card=ClubCardOut(
            id=card.id, serial_number=card.serial_number, player=PlayerOut.model_validate(card.player),
            acquired_at=card.acquired_at, is_in_lineup=False,
        ),
        budget=club.budget,
    )
