import random

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.club_card import ClubCard
from app.models.club_card_availability import ClubCardAvailability
from app.models.tournament_match import TournamentMatch
from app.services.lineup_service import CATEGORY_POSITIONS, FORMATION_SLOTS, calculate_base_strength

SUBSTITUTION_PENALTY = 0.5


def _card_to_actor(card: ClubCard, category: str) -> dict:
    return {
        "club_card_id": card.id, "player_id": card.player_id, "name": card.player.display_name,
        "rating": card.player.rating, "position": card.player.position.value, "category": category,
    }


async def resolve_match_lineup(db: AsyncSession, club_id: int) -> tuple[list[dict], bool]:
    """Returns (engine-ready lineup list, had_substitution). Substitutes any
    slot whose card is currently suspended (ClubCardAvailability.rounds_remaining
    > 0) from the bench — any ClubCard for this club not currently in the
    lineup — same category first, any category as fallback."""
    from app.services.club_squad_service import _get_or_none_lineup

    lineup = await _get_or_none_lineup(db, club_id)
    if lineup is None:
        return [], False

    by_slot = {lc.slot_code: lc.club_card for lc in lineup.cards}
    lineup_card_ids = {lc.club_card_id for lc in lineup.cards}

    suspended_ids: set[int] = set()
    if lineup_card_ids:
        rows = (
            await db.execute(
                select(ClubCardAvailability.club_card_id)
                .where(ClubCardAvailability.club_card_id.in_(lineup_card_ids), ClubCardAvailability.rounds_remaining > 0)
            )
        ).scalars().all()
        suspended_ids = set(rows)

    bench_cards = (
        await db.execute(
            select(ClubCard).where(ClubCard.club_id == club_id, ClubCard.id.notin_(lineup_card_ids or [0]))
            .options(joinedload(ClubCard.player))
        )
    ).unique().scalars().all()

    used_bench_ids: set[int] = set()
    had_substitution = False
    result: list[dict] = []

    for slot in FORMATION_SLOTS:
        card = by_slot.get(slot.code)
        if card is None or card.id in suspended_ids:
            had_substitution = True
            candidates = [b for b in bench_cards if b.id not in used_bench_ids and b.player.position in CATEGORY_POSITIONS[slot.category]]
            if not candidates:
                candidates = [b for b in bench_cards if b.id not in used_bench_ids]
            if candidates:
                sub = random.choice(candidates)
                used_bench_ids.add(sub.id)
                result.append(_card_to_actor(sub, slot.category))
            # else: no bench card available at all — slot stays unfilled, club
            # effectively plays a player short there; rare (needs >4 simultaneous
            # suspensions with an empty matching bench), not specially handled.
        else:
            result.append(_card_to_actor(card, slot.category))

    return result, had_substitution


async def form_multiplier(db: AsyncSession, club_id: int, config) -> float:
    matches = (
        await db.execute(
            select(TournamentMatch)
            .where(or_(TournamentMatch.club_a_id == club_id, TournamentMatch.club_b_id == club_id))
            .order_by(TournamentMatch.simulated_at.desc())
            .limit(config.club_form_window_matches)
        )
    ).scalars().all()
    delta = 0
    for m in matches:
        my_score, opp_score = (m.score_a, m.score_b) if m.club_a_id == club_id else (m.score_b, m.score_a)
        if my_score > opp_score:
            delta += 1
        elif my_score < opp_score:
            delta -= 1
    return 1 + delta * float(config.club_form_bonus_per_result)


async def match_strength(db: AsyncSession, club_id: int, config) -> tuple[int, list[dict]]:
    """Returns (final strength, engine-ready lineup) — bundled together since
    Task 14's orchestration needs both from one lineup resolution pass."""
    lineup, had_substitution = await resolve_match_lineup(db, club_id)
    cards_with_slots = [
        (type("Wrapped", (), {"player": type("P", (), {
            "position": _pos_enum(c["position"]), "rating": c["rating"], "rarity": None, "club": None, "country": None,
        })})(), slot)
        for c, slot in zip(lineup, FORMATION_SLOTS)
    ]
    # NOTE: calculate_base_strength needs real ClubCard/Player ORM objects
    # (it reads .player.rarity/.club/.country for the chemistry bonus), not
    # the engine's plain actor dicts — see Task 14, which calls this
    # function with the actual ORM cards fetched during resolve_match_lineup
    # rather than reconstructing fakes here. This function's real
    # implementation is finished in Task 14 once that ORM-object plumbing
    # is available; for now it returns a rating-average approximation.
    base = sum(c["rating"] for c in lineup) // max(len(lineup), 1) if lineup else 0
    if had_substitution:
        base = round(base * SUBSTITUTION_PENALTY)
    multiplier = await form_multiplier(db, club_id, config)
    return max(1, round(base * multiplier)), lineup


def _pos_enum(value: str):
    from app.models.enums import Position
    return Position(value)
