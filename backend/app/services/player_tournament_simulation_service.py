import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.card import UserCard
from app.models.enums import NotificationType, TransactionType, TournamentStatus
from app.models.player_tournament import (
    PlayerTournament, PlayerTournamentMatch, PlayerTournamentParticipant, PlayerTournamentResult,
    PlayerTournamentStanding,
)
from app.models.tournament_simulation_slot_log import TournamentSimulationSlotLog
from app.models.user import User
from app.services import personal_squad_service, tournament_match_engine, wallet_service
from app.services.club_formation_service import get_formation_slots
from app.services.club_tactical_matchup_service import build_side
from app.services.game_config_service import get_config
from app.services.lineup_service import FormationSlot
from app.services.notification_service import notify
from app.services.player_tournament_fixture_service import TOTAL_ROUNDS, generate_fixtures
from app.services.player_tournament_standing_service import apply_match_result, rank_standings

logger = logging.getLogger(__name__)

SLOT_KIND = "player_tournament_round"


@dataclass
class _EngineCard:
    """Adapter so the club-tuned engine sees a UserCard as (id, player_id,
    player.{display_name, rating, position, rarity, club, country, ...});
    rating includes the diamond upgrade bonus earned by that specific copy."""

    id: int
    player_id: int
    player: SimpleNamespace


def _engine_card(card: UserCard) -> _EngineCard:
    p = card.player
    return _EngineCard(
        id=card.id, player_id=card.player_id,
        # No diamond_rating_bonus on the adapter itself: the bonus is already
        # folded into player.rating, and calculate_base_strength would add it
        # again via getattr(card, "diamond_rating_bonus", 0).
        player=SimpleNamespace(
            display_name=p.display_name, position=p.position, rating=min(99, p.rating + card.diamond_rating_bonus),
            rarity=p.rarity, club=p.club, country=p.country,
            attack_rating=getattr(p, "attack_rating", None), defense_rating=getattr(p, "defense_rating", None),
        ),
    )


@dataclass
class _Side:
    side: object  # ClubTacticalSide
    lineup: list[dict]


async def _build_side(db: AsyncSession, user_id: int, *, is_home: bool) -> _Side | None:
    """None when the player cannot field a full starting XI (cards sold or
    traded away since applying). Stadium boost only applies to the home side
    (see player_tournament_fixture_service.generate_fixtures: user_a_id is
    always home for a given fixture row) — the away side gets no stadium
    bonus regardless of what stadium it owns."""
    squad, pairs = await personal_squad_service.resolve_active_squad(db, user_id)
    if len(pairs) != len(get_formation_slots(squad.formation)):
        return None
    with_slots: list[tuple[_EngineCard, FormationSlot]] = [(_engine_card(c), slot) for c, slot in pairs]
    coach = squad.user_coach_card.coach if squad.user_coach_card else None
    stadium_multiplier = (
        1.0 + float(squad.user_stadium_card.stadium.boost_pct) if is_home and squad.user_stadium_card else 1.0
    )
    side = build_side(with_slots, squad.mentality, squad.playstyle, coach=coach, stadium_multiplier=stadium_multiplier)
    lineup = [
        {
            "club_card_id": c.id, "player_id": c.player_id, "name": c.player.display_name,
            "rating": c.player.rating, "position": c.player.position.value, "category": slot.category,
        }
        for c, slot in with_slots
    ]
    return _Side(side=side, lineup=lineup)


async def _lock_tournament(db: AsyncSession, tournament_id: int) -> PlayerTournament:
    result = await db.execute(
        select(PlayerTournament).where(PlayerTournament.id == tournament_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _credit(
    db: AsyncSession, user_id: int, amount: int, tx_type: TransactionType, description: str, tournament_id: int,
) -> None:
    if amount <= 0:
        return
    user = await wallet_service.lock_user_for_update(db, user_id)
    await wallet_service.credit_coins(
        db, user, amount, tx_type, description,
        related_object_type="player_tournament", related_object_id=tournament_id,
    )


def _reward_for(config, own: int, opp: int) -> int:
    if own > opp:
        return config.ptour_match_reward_win
    if own < opp:
        return config.ptour_match_reward_loss
    return config.ptour_match_reward_draw


def _at(values: list, index: int) -> int:
    return int(values[index]) if 0 <= index < len(values) else 0


async def _play_match(
    db: AsyncSession, user_a_id: int, user_b_id: int, names: dict[int, str], config,
) -> tuple[int, int, list]:
    side_a = await _build_side(db, user_a_id, is_home=True)
    side_b = await _build_side(db, user_b_id, is_home=False)
    if side_a is not None and side_b is not None:
        result = tournament_match_engine.simulate_match(
            side_a.side, side_b.side, side_a.lineup, side_b.lineup, config, names[user_a_id], names[user_b_id],
        )
        return result.score_a, result.score_b, result.event_log
    if side_a is None and side_b is None:
        return 0, 0, []
    return (0, 3, []) if side_a is None else (3, 0, [])


async def simulate_next_round(db: AsyncSession, slot_key: str | None = None) -> list[PlayerTournamentMatch]:
    """Simulates the next round of every active player tournament, updates
    standings, pays per-match rewards, and on round 30 concludes the
    tournament (place rewards + rating). Idempotency: a duplicate slot_key is
    a no-op (try-insert into TournamentSimulationSlotLog); concurrent callers
    are serialized by the per-tournament row lock, and the loser re-reads
    rounds_simulated and skips — same design as
    tournament_simulation_service.simulate_next_round (clubs)."""
    if slot_key is not None:
        try:
            db.add(TournamentSimulationSlotLog(kind=SLOT_KIND, slot_key=slot_key))
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return []

    config = await get_config(db)
    candidates = (
        await db.execute(
            select(PlayerTournament.id, PlayerTournament.rounds_simulated)
            .where(PlayerTournament.status == TournamentStatus.active, PlayerTournament.rounds_simulated < TOTAL_ROUNDS)
        )
    ).all()

    all_matches: list[PlayerTournamentMatch] = []
    for tournament_id, observed_rounds in candidates:
        try:
            tournament = await _lock_tournament(db, tournament_id)
            round_number = observed_rounds + 1
            if tournament.status != TournamentStatus.active or tournament.rounds_simulated >= round_number:
                continue

            participants = (
                await db.execute(
                    select(PlayerTournamentParticipant)
                    .where(PlayerTournamentParticipant.tournament_id == tournament.id)
                    .order_by(PlayerTournamentParticipant.id)
                )
            ).scalars().all()
            user_ids = [p.user_id for p in participants]
            # Lock every participant in ascending id order up front: trade accept
            # locks its two users sorted by id, so a per-match fixture-order lock
            # could deadlock against a concurrent trade between participants.
            users = (
                await db.execute(
                    select(User).where(User.id.in_(user_ids)).order_by(User.id)
                    .with_for_update(of=User).execution_options(populate_existing=True)
                )
            ).scalars().all()
            names = {u.id: u.full_display_name() for u in users}
            standings = {
                s.user_id: s for s in (
                    await db.execute(select(PlayerTournamentStanding).where(PlayerTournamentStanding.tournament_id == tournament.id)
                        .order_by(PlayerTournamentStanding.user_id))
                ).scalars().all()
            }

            round_matches: list[PlayerTournamentMatch] = []
            for _, user_a_id, user_b_id in (f for f in generate_fixtures(user_ids) if f[0] == round_number):
                score_a, score_b, event_log = await _play_match(db, user_a_id, user_b_id, names, config)
                match = PlayerTournamentMatch(
                    tournament_id=tournament.id, round_number=round_number, user_a_id=user_a_id, user_b_id=user_b_id,
                    score_a=score_a, score_b=score_b, event_log=event_log, simulated_at=datetime.now(timezone.utc),
                )
                db.add(match)
                apply_match_result(standings[user_a_id], standings[user_b_id], score_a, score_b)

                description = f"Матч {round_number}-го тура турнира"
                for uid in sorted((user_a_id, user_b_id)):  # stable lock order
                    own, opp = (score_a, score_b) if uid == user_a_id else (score_b, score_a)
                    await _credit(
                        db, uid, _reward_for(config, own, opp), TransactionType.player_tournament_match_reward,
                        description, tournament.id,
                    )
                # No score in the notification: the app reveals the match step by
                # step (TournamentMatchReplay); a push would spoil it.
                for uid in (user_a_id, user_b_id):
                    await notify(
                        db, uid, NotificationType.player_tournament_match, "Матч сыгран",
                        f"Сыгран матч {round_number}-го тура турнира — смотри результат в приложении",
                        related_object_type="player_tournament", related_object_id=tournament.id,
                    )
                round_matches.append(match)

            tournament.rounds_simulated = round_number
            db.add(tournament)

            if round_number == TOTAL_ROUNDS:
                await db.flush()
                season_matches = (
                    await db.execute(select(PlayerTournamentMatch).where(PlayerTournamentMatch.tournament_id == tournament.id))
                ).scalars().all()
                await conclude_tournament(db, tournament, list(standings.values()), list(season_matches), config)

            await db.commit()
            all_matches.extend(round_matches)
        except Exception:
            await db.rollback()
            logger.exception("Player tournament %s round simulation failed", tournament_id)
            # rollback expired the session's objects; re-fetch before reuse.
            config = await get_config(db)
            continue

    return all_matches


async def conclude_tournament(
    db: AsyncSession, tournament: PlayerTournament, standings: list[PlayerTournamentStanding],
    matches: list[PlayerTournamentMatch], config,
) -> list[PlayerTournamentResult]:
    ranked = rank_standings(standings, matches)
    results: list[PlayerTournamentResult] = []
    for index, standing in enumerate(ranked):
        rank = index + 1
        coins = _at(config.ptour_place_rewards, index)
        stars_delta = _at(config.ptour_stars_by_place, index)
        cup_awarded = rank == 1

        await _credit(
            db, standing.user_id, coins, TransactionType.player_tournament_place_reward,
            f"Награда за {rank}-е место в турнире #{tournament.id}", tournament.id,
        )
        user = await wallet_service.lock_user_for_update(db, standing.user_id)
        user.tournament_stars_count += stars_delta
        if cup_awarded:
            user.tournament_cups_count += 1
        db.add(user)

        result = PlayerTournamentResult(
            tournament_id=tournament.id, user_id=standing.user_id, final_rank=rank,
            coins_awarded=coins, stars_delta=stars_delta, cup_awarded=cup_awarded,
        )
        db.add(result)
        results.append(result)

        await notify(
            db, standing.user_id, NotificationType.player_tournament_results_ready, "Турнир завершён",
            f"Ты занял {rank}-е место в турнире — загляни за результатами!",
            related_object_type="player_tournament", related_object_id=tournament.id,
        )

    tournament.status = TournamentStatus.completed
    db.add(tournament)
    return results
