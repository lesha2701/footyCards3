import random
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.club import Club
from app.models.club_card import ClubCard
from app.models.club_card_availability import ClubCardAvailability
from app.models.enums import NotificationType, TournamentStatus
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_match import TournamentMatch
from app.models.tournament_simulation_slot_log import TournamentSimulationSlotLog
from app.models.tournament_standing import TournamentClubStanding
from app.services import tournament_match_engine, tournament_notification_service
from app.services.game_config_service import get_config
from app.services.lineup_service import CATEGORY_POSITIONS, FORMATION_SLOTS, FormationSlot, calculate_base_strength
from app.services.tournament_fixture_service import generate_fixtures
from app.services.tournament_reward_service import conclude_tournament
from app.services.tournament_standing_service import apply_match_result

SUBSTITUTION_PENALTY = 0.5


def _card_to_actor(card: ClubCard, category: str) -> dict:
    return {
        "club_card_id": card.id, "player_id": card.player_id, "name": card.player.display_name,
        "rating": card.player.rating, "position": card.player.position.value, "category": category,
    }


async def resolve_match_lineup(
    db: AsyncSession, club_id: int
) -> tuple[list[dict], bool, list[tuple[ClubCard, FormationSlot]]]:
    """Returns (engine-ready lineup list, had_substitution, cards_with_slots).
    Substitutes any slot whose card is currently suspended
    (ClubCardAvailability.rounds_remaining > 0) from the bench — any ClubCard
    for this club not currently in the lineup — same category first, any
    category as fallback. `cards_with_slots` mirrors `result` but carries the
    real (ClubCard, FormationSlot) ORM pairs actually used per slot (post-
    substitution), so callers (match_strength) can feed them straight into
    lineup_service.calculate_base_strength instead of reconstructing fakes."""
    from app.services.club_squad_service import _get_or_none_lineup

    lineup = await _get_or_none_lineup(db, club_id)
    if lineup is None:
        return [], False, []

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
    cards_with_slots: list[tuple[ClubCard, FormationSlot]] = []

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
                cards_with_slots.append((sub, slot))
            # else: no bench card available at all — slot stays unfilled, club
            # effectively plays a player short there; rare (needs >4 simultaneous
            # suspensions with an empty matching bench), not specially handled.
        else:
            result.append(_card_to_actor(card, slot.category))
            cards_with_slots.append((card, slot))

    return result, had_substitution, cards_with_slots


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
    the orchestration in simulate_next_round needs both from one lineup
    resolution pass. Uses the real lineup_service.calculate_base_strength
    (rating*position-fit*rarity-bonus, plus a club/country chemistry bonus)
    against the actual post-substitution (ClubCard, FormationSlot) pairs —
    no more rating-average stopgap."""
    lineup, had_substitution, cards_with_slots = await resolve_match_lineup(db, club_id)
    base = calculate_base_strength(cards_with_slots)
    if had_substitution:
        base = round(base * SUBSTITUTION_PENALTY)
    multiplier = await form_multiplier(db, club_id, config)
    return max(1, round(base * multiplier)), lineup


# --- Round orchestration ------------------------------------------------


async def _lock_tournament(db: AsyncSession, tournament_id: int) -> Tournament:
    """Standard `_lock_club`-style row lock — Tournament is a normal per-row
    entity (no singleton-state precedent needed, unlike
    tournament_queue_service._lock_queue_state). populate_existing=True for
    the same reason every other lock in this codebase needs it: without it, a
    Tournament already sitting in the session's identity map (e.g. the
    caller already loaded it) would be returned as-is instead of the freshly
    locked row."""
    result = await db.execute(
        select(Tournament).where(Tournament.id == tournament_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _decay_availability(db: AsyncSession, club_id: int) -> None:
    """Ticks every one of this club's active suspensions down by one round —
    called once per club per round, right after that club's match has been
    simulated (see the design spec: rounds_remaining only ticks down "when
    the owning club has a match simulated", not for free). Deletes the row
    once it reaches 0 rather than leaving a stale 0 row around."""
    rows = (
        await db.execute(
            select(ClubCardAvailability)
            .join(ClubCard, ClubCard.id == ClubCardAvailability.club_card_id)
            .where(ClubCard.club_id == club_id)
        )
    ).scalars().all()
    for row in rows:
        row.rounds_remaining -= 1
        if row.rounds_remaining <= 0:
            await db.delete(row)
        else:
            db.add(row)


async def _apply_engine_result(db: AsyncSession, engine_result: "tournament_match_engine.MatchResult") -> None:
    """Persists the new suspensions this match itself produced (injuries:
    1-3 future rounds; red cards: next round only). Must run AFTER
    _decay_availability for both clubs in the same round — a suspension
    minted by this match must still hold for the *next* round, not be
    decremented to 0 in the very round it was earned. A club_card_id that
    picked up both a red card and its associated injury roll in the same
    match keeps the longer of the two (max), rather than one overwriting
    the other."""
    for club_card_id, rounds in [*engine_result.red_cards, *engine_result.injuries]:
        existing = (
            await db.execute(select(ClubCardAvailability).where(ClubCardAvailability.club_card_id == club_card_id))
        ).scalar_one_or_none()
        if existing is None:
            db.add(ClubCardAvailability(club_card_id=club_card_id, rounds_remaining=rounds))
        else:
            existing.rounds_remaining = max(existing.rounds_remaining, rounds)
            db.add(existing)


async def simulate_next_round(db: AsyncSession, slot_key: str | None = None) -> list[TournamentMatch]:
    """Simulates the next round for every tournament that still has one due
    (status active, rounds_simulated < 14), persists TournamentMatch rows,
    updates standings, decays availability suspensions, and — on round 14 —
    concludes the tournament (rewards + status=completed) via
    tournament_reward_service.conclude_tournament.

    Concurrency: the target round number for each tournament is captured
    from the pre-lock read (`observed_rounds_simulated`), before
    `_lock_tournament`'s SELECT ... FOR UPDATE. Two concurrent calls that
    both observe the same "next round is N" snapshot will both try to lock
    the same Tournament row; the loser only proceeds after the winner
    commits, at which point it re-reads rounds_simulated with
    populate_existing=True and sees it already >= the round it meant to
    simulate — so it skips that tournament entirely instead of simulating
    a further round on top. This is what makes both round-1 idempotency and
    round-14 (reward distribution) idempotency hold under a genuine race —
    see test_simulate_next_round_is_idempotent_under_concurrent_calls and
    test_round_14_reward_distribution_cannot_double_fire_under_concurrency.

    That per-Tournament lock only handles concurrent-caller races, though —
    it does NOT make a duplicate/late fire hours or days apart safe, since
    each such call legitimately re-reads rounds_simulated and simulates a
    genuine new round. Time-based idempotency (surviving a bot restart that
    resets in-memory scheduling state) is handled separately, by the
    caller-supplied slot_key try-insert against TournamentSimulationSlotLog
    below — a duplicate slot_key raises IntegrityError and this function
    returns an empty list without simulating anything.
    """
    if slot_key is not None:
        try:
            db.add(TournamentSimulationSlotLog(kind="simulate_round", slot_key=slot_key))
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return []

    config = await get_config(db)
    candidates = (
        await db.execute(
            select(Tournament.id, Tournament.rounds_simulated)
            .where(Tournament.status == TournamentStatus.active, Tournament.rounds_simulated < 14)
        )
    ).all()

    all_matches: list[TournamentMatch] = []

    for tournament_id, observed_rounds_simulated in candidates:
        tournament = await _lock_tournament(db, tournament_id)
        target_round_number = observed_rounds_simulated + 1
        if tournament.status != TournamentStatus.active or tournament.rounds_simulated >= target_round_number:
            # A concurrent caller already simulated this round (or already
            # concluded the tournament) between our pre-lock read and
            # acquiring the lock — nothing left to do here.
            continue

        round_number = target_round_number
        participants = (
            await db.execute(
                select(TournamentClub).where(TournamentClub.tournament_id == tournament.id).order_by(TournamentClub.id)
            )
        ).scalars().all()
        club_ids = [p.club_id for p in participants]
        withdrawn_ids = {p.club_id for p in participants if p.is_withdrawn}

        club_names = {c.id: c.name for c in (await db.execute(select(Club).where(Club.id.in_(club_ids)))).scalars().all()}

        fixtures = [f for f in generate_fixtures(club_ids) if f[0] == round_number]
        standings_rows = (
            await db.execute(select(TournamentClubStanding).where(TournamentClubStanding.tournament_id == tournament.id))
        ).scalars().all()
        standings_by_club = {s.club_id: s for s in standings_rows}

        round_matches: list[TournamentMatch] = []
        for _, club_a_id, club_b_id in fixtures:
            if club_a_id in withdrawn_ids or club_b_id in withdrawn_ids:
                # Withdrawn club auto-loses 0-3, no engine run, no availability
                # decay (there's no real match being simulated for it). No
                # club is actually withdrawn yet in this codebase (Task 15
                # will be the first thing to set TournamentClub.is_withdrawn),
                # so this branch is forward-looking but inert today.
                score_a, score_b = (0, 3) if club_a_id in withdrawn_ids else (3, 0)
                match = TournamentMatch(
                    tournament_id=tournament.id, round_number=round_number, club_a_id=club_a_id, club_b_id=club_b_id,
                    score_a=score_a, score_b=score_b, event_log=[], simulated_at=datetime.now(timezone.utc),
                )
                db.add(match)
                apply_match_result(standings_by_club[club_a_id], standings_by_club[club_b_id], score_a, score_b)
                round_matches.append(match)
                continue

            strength_a, lineup_a = await match_strength(db, club_a_id, config)
            strength_b, lineup_b = await match_strength(db, club_b_id, config)
            engine_result = tournament_match_engine.simulate_match(
                strength_a, strength_b, lineup_a, lineup_b, config,
                club_names[club_a_id], club_names[club_b_id],
            )

            match = TournamentMatch(
                tournament_id=tournament.id, round_number=round_number, club_a_id=club_a_id, club_b_id=club_b_id,
                score_a=engine_result.score_a, score_b=engine_result.score_b,
                event_log=engine_result.event_log, simulated_at=datetime.now(timezone.utc),
            )
            db.add(match)
            apply_match_result(standings_by_club[club_a_id], standings_by_club[club_b_id], engine_result.score_a, engine_result.score_b)

            # Decay pre-existing suspensions for both clubs now that their
            # match has been played, BEFORE this same match's own new
            # suspensions are registered below.
            await _decay_availability(db, club_a_id)
            await _decay_availability(db, club_b_id)
            await _apply_engine_result(db, engine_result)

            round_matches.append(match)

            await tournament_notification_service.notify_club_members(
                db, club_a_id, NotificationType.club_match, "Матч сыгран",
                f"Твой клуб сыграл матч {round_number}-го тура турнира — счёт {engine_result.score_a}:{engine_result.score_b}",
                related_object_type="club_match", related_object_id=tournament.id,
            )
            await tournament_notification_service.notify_club_members(
                db, club_b_id, NotificationType.club_match, "Матч сыгран",
                f"Твой клуб сыграл матч {round_number}-го тура турнира — счёт {engine_result.score_b}:{engine_result.score_a}",
                related_object_type="club_match", related_object_id=tournament.id,
            )

        tournament.rounds_simulated = round_number
        db.add(tournament)

        if round_number == 14:
            # rank_standings' head-to-head tie-break needs the full season's
            # matches, not just this round's 4 — autoflush makes this SELECT
            # see the round_matches just db.add()-ed above alongside every
            # earlier round already committed in prior calls.
            season_matches = (
                await db.execute(select(TournamentMatch).where(TournamentMatch.tournament_id == tournament.id))
            ).scalars().all()
            await conclude_tournament(db, tournament, list(standings_by_club.values()), list(season_matches))

        await db.commit()
        all_matches.extend(round_matches)

    return all_matches
