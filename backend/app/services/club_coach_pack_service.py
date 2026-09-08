from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.exceptions import NotFoundError
from app.models.club import Club
from app.models.club_coach_card import ClubCoachCard
from app.models.club_coach_pack import ClubCoachPack
from app.models.club_coach_pack_opening import ClubCoachPackOpening, ClubCoachPackOpeningCard
from app.models.coach import Coach
from app.models.enums import ClubBudgetTransactionType, ClubCoachCardSource
from app.models.user import User
from app.schemas.club_coach_pack import ClubCoachPackOpenResult, ClubCoachPackOut, OpenedClubCoachCardOut
from app.schemas.club_squad import ClubCoachCardOut
from app.services.club_budget_service import debit_club_budget
from app.services.club_service import _lock_club, _require_manager, _require_membership
from app.services.pack_service import pick_random_coach, roll_rarities


async def list_club_coach_packs(db: AsyncSession) -> list[ClubCoachPackOut]:
    result = await db.execute(
        select(ClubCoachPack).where(ClubCoachPack.is_active.is_(True)).options(joinedload(ClubCoachPack.rarity_probabilities)).order_by(ClubCoachPack.sort_order)
    )
    return result.unique().scalars().all()


async def _create_club_coach_card(
    db: AsyncSession, club_id: int, coach_id: int, source: ClubCoachCardSource, source_ref_id: Optional[int] = None
) -> ClubCoachCard:
    """Mirrors club_card_service.create_club_card exactly, but against the
    separate `Coach.next_club_serial_number` counter (reserved for this
    purpose since the Coach model was introduced — see its own docstring
    comment) — club coach packs must never affect personal-card serial-
    number scarcity, and the counter must be read-and-incremented under a
    row lock rather than a racy `MAX(serial_number) + 1` scan, matching
    every other serial-number allocation in this codebase."""
    coach = await db.get(Coach, coach_id)
    await db.refresh(coach, attribute_names=["next_club_serial_number"], with_for_update=True)
    serial_number = coach.next_club_serial_number
    coach.next_club_serial_number += 1
    db.add(coach)

    card = ClubCoachCard(club_id=club_id, coach_id=coach_id, source=source, source_ref_id=source_ref_id, serial_number=serial_number)
    db.add(card)
    await db.flush()
    return card


def _to_club_coach_card_out(card: ClubCoachCard) -> ClubCoachCardOut:
    return ClubCoachCardOut(id=card.id, serial_number=card.serial_number, coach=card.coach, acquired_at=card.acquired_at)


async def _get_result_for_existing_opening(db: AsyncSession, opening: ClubCoachPackOpening) -> ClubCoachPackOpenResult:
    pack = await db.get(ClubCoachPack, opening.club_coach_pack_id, options=[joinedload(ClubCoachPack.rarity_probabilities)])
    cards_result = await db.execute(select(ClubCoachPackOpeningCard).where(ClubCoachPackOpeningCard.opening_id == opening.id))
    opening_cards = cards_result.scalars().all()
    # `ClubCoachCard.coach` is `lazy="joined"` (always eager-loaded), but that doesn't cascade
    # to `Coach.boosts` — CoachOut nests boosts, so it needs its own explicit eager load here,
    # same as pick_random_coach's own selectinload(Coach.boosts) in pack_service.py.
    club_coach_cards = {
        c.id: c
        for c in (
            await db.execute(
                select(ClubCoachCard)
                .where(ClubCoachCard.id.in_([oc.club_coach_card_id for oc in opening_cards]))
                .options(joinedload(ClubCoachCard.coach).selectinload(Coach.boosts))
            )
        ).scalars().all()
    }
    # `Club` (not a placeholder) — confirmed against club_pack_service.py's
    # own `_get_result_for_existing_opening`, which re-fetches the club the
    # same way for its idempotent-replay path.
    club_row = await db.get(Club, opening.club_id)
    return ClubCoachPackOpenResult(
        pack=ClubCoachPackOut.model_validate(pack),
        cards=[
            OpenedClubCoachCardOut(card=_to_club_coach_card_out(club_coach_cards[oc.club_coach_card_id]), is_new=oc.is_new_coach)
            for oc in opening_cards
        ],
        new_budget=club_row.budget,
    )


async def open_club_coach_pack(
    db: AsyncSession, user: User, club_coach_pack_id: int, idempotency_key: Optional[str]
) -> ClubCoachPackOpenResult:
    membership = await _require_membership(db, user.id)
    _require_manager(membership)

    if idempotency_key:
        existing = await db.execute(
            select(ClubCoachPackOpening).where(
                ClubCoachPackOpening.club_id == membership.club_id, ClubCoachPackOpening.idempotency_key == idempotency_key
            )
        )
        existing_opening = existing.scalar_one_or_none()
        if existing_opening is not None:
            return await _get_result_for_existing_opening(db, existing_opening)

    pack = await db.get(ClubCoachPack, club_coach_pack_id, options=[joinedload(ClubCoachPack.rarity_probabilities)])
    if pack is None or not pack.is_active:
        raise NotFoundError("Клубный пак тренеров не найден")

    club = await _lock_club(db, membership.club_id)
    await debit_club_budget(
        db, club, pack.price, ClubBudgetTransactionType.coach_pack_purchase, f"Открытие пака «{pack.name}»", "club_coach_pack", pack.id
    )

    # Captured as a plain int (not a `club.id` attribute access) for reuse in the
    # `except IntegrityError` fallback below — see club_pack_service.open_club_pack's own
    # comment on why: `await db.rollback()` there expires every ORM object still attached to
    # this session, and touching an expired attribute outside SQLAlchemy's own async call
    # plumbing raises `MissingGreenlet`, not a lazy-load.
    club_id = club.id

    opening = ClubCoachPackOpening(
        club_id=club_id, club_coach_pack_id=pack.id, opened_by_user_id=user.id, price_paid=pack.price, idempotency_key=idempotency_key
    )

    try:
        db.add(opening)
        await db.flush()

        existing_coach_ids_result = await db.execute(select(ClubCoachCard.coach_id).where(ClubCoachCard.club_id == club_id))
        existing_coach_ids = set(existing_coach_ids_result.scalars().all())

        rarities = roll_rarities(pack.rarity_probabilities, pack.card_count, pack.guaranteed_min_rarity)
        opened_cards: list[OpenedClubCoachCardOut] = []
        for rarity in rarities:
            coach = await pick_random_coach(db, rarity)
            is_new = coach.id not in existing_coach_ids
            existing_coach_ids.add(coach.id)
            club_coach_card = await _create_club_coach_card(db, club_id, coach.id, ClubCoachCardSource.club_pack, opening.id)
            db.add(ClubCoachPackOpeningCard(opening_id=opening.id, club_coach_card_id=club_coach_card.id, is_new_coach=is_new))
            opened_cards.append(OpenedClubCoachCardOut(card=_to_club_coach_card_out(club_coach_card), is_new=is_new))

        await db.commit()
    except IntegrityError:
        # Same idempotency-key race as open_club_pack's own handler — Postgres enforces the
        # (club_id, idempotency_key) unique constraint at INSERT/flush time, not at COMMIT
        # time, so a genuine concurrent duplicate can raise as early as `db.flush()` above.
        await db.rollback()
        if not idempotency_key:
            raise
        existing = await db.execute(
            select(ClubCoachPackOpening).where(ClubCoachPackOpening.club_id == club_id, ClubCoachPackOpening.idempotency_key == idempotency_key)
        )
        return await _get_result_for_existing_opening(db, existing.scalar_one())

    await db.refresh(club)
    return ClubCoachPackOpenResult(pack=ClubCoachPackOut.model_validate(pack), cards=opened_cards, new_budget=club.budget)
