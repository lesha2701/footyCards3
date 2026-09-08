import random
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.exceptions import NotFoundError
from app.models.club import Club
from app.models.club_card import ClubCard
from app.models.club_coach_card import ClubCoachCard
from app.models.club_pack import ClubPack
from app.models.club_pack_opening import ClubPackOpening, ClubPackOpeningCard
from app.models.coach import Coach
from app.models.enums import ClubBudgetTransactionType, ClubCardSource, ClubCoachCardSource
from app.models.user import User
from app.schemas.club_pack import ClubPackOut
from app.schemas.club_pack_open import ClubPackOpenResult, OpenedClubPackItemOut
from app.schemas.club_squad import ClubCardOut, ClubCoachCardOut
from app.services.club_card_service import create_club_card, create_club_coach_card
from app.services.club_budget_service import debit_club_budget
from app.services.club_service import _lock_club, _require_manager, _require_membership
from app.services.pack_service import pick_random_coach, pick_random_player, roll_rarities


async def list_club_packs(db: AsyncSession) -> list[ClubPackOut]:
    result = await db.execute(
        select(ClubPack).where(ClubPack.is_active.is_(True)).options(joinedload(ClubPack.rarity_probabilities)).order_by(ClubPack.sort_order)
    )
    return result.unique().scalars().all()


def _player_item(club_card: ClubCard, is_new: bool) -> OpenedClubPackItemOut:
    return OpenedClubPackItemOut(
        kind="player",
        card=ClubCardOut(id=club_card.id, serial_number=club_card.serial_number, player=club_card.player, acquired_at=club_card.acquired_at, is_in_lineup=False),
        is_new=is_new,
    )


def _coach_item(club_coach_card: ClubCoachCard, is_new: bool) -> OpenedClubPackItemOut:
    return OpenedClubPackItemOut(
        kind="coach",
        coach_card=ClubCoachCardOut(id=club_coach_card.id, serial_number=club_coach_card.serial_number, coach=club_coach_card.coach, acquired_at=club_coach_card.acquired_at),
        is_new=is_new,
    )


async def _get_result_for_existing_opening(db: AsyncSession, opening: ClubPackOpening) -> ClubPackOpenResult:
    pack = await db.get(ClubPack, opening.club_pack_id, options=[joinedload(ClubPack.rarity_probabilities)])
    cards_result = await db.execute(select(ClubPackOpeningCard).where(ClubPackOpeningCard.opening_id == opening.id))
    opening_cards = cards_result.scalars().all()

    club_card_ids = [oc.club_card_id for oc in opening_cards if oc.club_card_id is not None]
    club_cards = {c.id: c for c in (await db.execute(select(ClubCard).where(ClubCard.id.in_(club_card_ids)))).scalars().all()} if club_card_ids else {}

    club_coach_card_ids = [oc.club_coach_card_id for oc in opening_cards if oc.club_coach_card_id is not None]
    club_coach_cards = (
        {
            c.id: c
            for c in (
                await db.execute(
                    select(ClubCoachCard).where(ClubCoachCard.id.in_(club_coach_card_ids)).options(joinedload(ClubCoachCard.coach).selectinload(Coach.boosts))
                )
            ).scalars().all()
        }
        if club_coach_card_ids
        else {}
    )

    items: list[OpenedClubPackItemOut] = []
    for oc in opening_cards:
        if oc.club_card_id is not None:
            items.append(_player_item(club_cards[oc.club_card_id], oc.is_new))
        else:
            items.append(_coach_item(club_coach_cards[oc.club_coach_card_id], oc.is_new))

    club_row = await db.get(Club, opening.club_id)
    return ClubPackOpenResult(opening_id=opening.id, pack=ClubPackOut.model_validate(pack), cards=items, new_budget=club_row.budget)


async def open_club_pack(db: AsyncSession, user: User, club_pack_id: int, idempotency_key: Optional[str]) -> ClubPackOpenResult:
    membership = await _require_membership(db, user.id)
    _require_manager(membership)

    if idempotency_key:
        existing = await db.execute(
            select(ClubPackOpening).where(ClubPackOpening.club_id == membership.club_id, ClubPackOpening.idempotency_key == idempotency_key)
        )
        existing_opening = existing.scalar_one_or_none()
        if existing_opening is not None:
            return await _get_result_for_existing_opening(db, existing_opening)

    pack = await db.get(ClubPack, club_pack_id, options=[joinedload(ClubPack.rarity_probabilities)])
    if pack is None or not pack.is_active:
        raise NotFoundError("Клубный пак не найден")

    club = await _lock_club(db, membership.club_id)
    await debit_club_budget(db, club, pack.price, ClubBudgetTransactionType.pack_purchase, f"Открытие пака «{pack.name}»", "club_pack", pack.id)

    # Captured as a plain int (not a `club.id` attribute access) for reuse in the
    # `except IntegrityError` fallback below — `await db.rollback()` there expires every ORM
    # object still attached to this session, and touching an expired attribute via a bare
    # (non-awaited) attribute access outside SQLAlchemy's own async call plumbing raises
    # `MissingGreenlet`, not a lazy-load; this was proven by an actual concurrent-race run
    # against real Postgres that hit exactly that crash before this was captured up front.
    club_id = club.id

    opening = ClubPackOpening(club_id=club_id, club_pack_id=pack.id, opened_by_user_id=user.id, price_paid=pack.price, idempotency_key=idempotency_key)

    try:
        db.add(opening)
        await db.flush()

        existing_player_ids_result = await db.execute(select(ClubCard.player_id).where(ClubCard.club_id == club_id))
        existing_player_ids = set(existing_player_ids_result.scalars().all())
        existing_coach_ids_result = await db.execute(select(ClubCoachCard.coach_id).where(ClubCoachCard.club_id == club_id))
        existing_coach_ids = set(existing_coach_ids_result.scalars().all())

        rarities = roll_rarities(pack.rarity_probabilities, pack.card_count, pack.guaranteed_min_rarity)
        opened_cards: list[OpenedClubPackItemOut] = []
        coach_drop_chance = float(pack.coach_drop_chance)
        for rarity in rarities:
            # Each slot is an independent coin flip against the pack's coach_drop_chance —
            # not a fixed count of coach slots — so a coach_drop_chance of e.g. 0.3 means every
            # slot has an independent 30% chance of resolving to a coach instead of a player.
            if coach_drop_chance > 0 and random.random() < coach_drop_chance:
                coach = await pick_random_coach(db, rarity)
                is_new = coach.id not in existing_coach_ids
                existing_coach_ids.add(coach.id)
                club_coach_card = await create_club_coach_card(db, club_id, coach.id, ClubCoachCardSource.club_pack, opening.id)
                db.add(ClubPackOpeningCard(opening_id=opening.id, club_card_id=None, club_coach_card_id=club_coach_card.id, is_new=is_new))
                opened_cards.append(_coach_item(club_coach_card, is_new))
            else:
                player = await pick_random_player(db, rarity)
                is_new = player.id not in existing_player_ids
                existing_player_ids.add(player.id)
                club_card = await create_club_card(db, club_id, player.id, ClubCardSource.club_pack, opening.id)
                db.add(ClubPackOpeningCard(opening_id=opening.id, club_card_id=club_card.id, club_coach_card_id=None, is_new=is_new))
                opened_cards.append(_player_item(club_card, is_new))

        await db.commit()
    except IntegrityError:
        # Postgres enforces the (club_id, idempotency_key) unique constraint at INSERT/flush
        # time, not at COMMIT time — so a genuine concurrent duplicate can raise here as early
        # as `db.flush()` above, not just from the final `db.commit()`. The try block must
        # therefore wrap the whole write sequence (initial insert through commit) so that no
        # matter where the violation actually fires, we discard ALL of this request's
        # in-progress work (the opening row AND any cards minted before the conflict was hit)
        # and fall back to returning the winning concurrent request's result.
        await db.rollback()
        if not idempotency_key:
            # A keyless request has no idempotency contract to honor: the unique constraint
            # is on (club_id, idempotency_key), and `idempotency_key IS NULL` would either
            # match an unrelated earlier keyless opening for the same club or raise from
            # `scalar_one()` (MultipleResultsFound/NoResultFound) — masking whatever the real
            # constraint violation actually was. Re-raising as an unhandled 500 isn't ideal
            # long-term, but is strictly better than silently returning a wrong opening.
            raise
        existing = await db.execute(
            select(ClubPackOpening).where(ClubPackOpening.club_id == club_id, ClubPackOpening.idempotency_key == idempotency_key)
        )
        return await _get_result_for_existing_opening(db, existing.scalar_one())

    await db.refresh(club)
    return ClubPackOpenResult(opening_id=opening.id, pack=ClubPackOut.model_validate(pack), cards=opened_cards, new_budget=club.budget)
