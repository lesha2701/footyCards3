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
from app.services import (
    card_skill_service, chemistry_service, path_match_service, path_service, personal_squad_service,
    tournament_match_engine, wallet_service,
)
from app.services.path_talent_effects import override_positions, with_bonus
from app.services.card_skill_effects import SNAPSHOT_VERSION, effect_for_card
from app.services.chemistry_service import ChemistryRules
from app.services.player_stats_service import card_rating_bonus
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
    # Frozen card-skill effect for this match (card_skill_effects.effect_for_card),
    # None when the card has no skill or the mechanic is off.
    skill: dict | None = None
    # Frozen «Начало пути» talent snapshot (path_talent_effects), None = none.
    talent: dict | None = None


def _engine_card(
    card: UserCard, config=None, chemistry_bonus: int = 0, talent: dict | None = None, talent_bonus: int = 0,
) -> _EngineCard:
    """chemistry_bonus: this card's neighbour-link chemistry bonus
    (chemistry_service, 0 while the mechanic is off) — folded into the match
    rating the engine reads, after the diamond/star bonus and before any zone
    profile / coach / stadium math. talent_bonus: its static «Начало пути»
    talents (kickoff), added on top; `talent` is the snapshot whose dynamic
    part the engine applies per chance."""
    p = card.player
    skill = effect_for_card(card.skill_code, card.skill_level, p.position, config) if config is not None else None
    if skill is not None:
        skill["player"] = p.display_name
    return _EngineCard(
        id=card.id, player_id=card.player_id, skill=skill, talent=talent,
        # No diamond/star bonus fields on the adapter itself: the bonus is
        # already folded into player.rating, and calculate_base_strength would
        # add it again via card_rating_bonus(card).
        player=SimpleNamespace(
            display_name=p.display_name, position=p.position,
            rating=with_bonus(
                chemistry_service.boosted_rating(min(99, p.rating + card_rating_bonus(card)), chemistry_bonus), talent_bonus,
            ),
            rarity=p.rarity, club=p.club, country=p.country,
            attack_rating=getattr(p, "attack_rating", None), defense_rating=getattr(p, "defense_rating", None),
        ),
    )


@dataclass
class _Side:
    side: object  # ClubTacticalSide
    lineup: list[dict]
    # {"team", "max", "cards": {card_id: points}} when chemistry was applied.
    chemistry: dict | None = None
    # «Начало пути»: path cards of the squad, whether any has a talent that
    # acts here, and the applied talent snapshot (when built with talents).
    path_cards: list | None = None
    talented: bool = False
    talents: dict | None = None

    @property
    def avg_rating(self) -> float:
        return sum(c["rating"] for c in self.lineup) / len(self.lineup) if self.lineup else 0.0

    def skill_snapshot(self) -> dict:
        return {str(c["club_card_id"]): c["skill"] for c in self.lineup if c.get("skill")}


async def _build_side(
    db: AsyncSession, user_id: int, *, is_home: bool, config=None, chemistry_rules: ChemistryRules | None = None,
    catalog=None, opponent_avg: float | None = None, with_talents: bool = False,
) -> _Side | None:
    """None when the player cannot field a full starting XI (cards sold or
    traded away since applying). Stadium boost only applies to the home side
    (see player_tournament_fixture_service.generate_fixtures: user_a_id is
    always home for a given fixture row) — the away side gets no stadium
    bonus regardless of what stadium it owns."""
    squad, pairs = await personal_squad_service.resolve_active_squad(db, user_id)
    if len(pairs) != len(get_formation_slots(squad.formation)):
        return None
    formation_slots = get_formation_slots(squad.formation)
    # chemistry_rules = the tournament's own frozen rules (PlayerTournament
    # .chemistry_rules), never the live GameConfig — see _play_match.
    coach = squad.user_coach_card.coach if squad.user_coach_card else None
    home_stadium = squad.user_stadium_card.stadium if is_home and squad.user_stadium_card else None
    # «Начало пути» talents (kickoff): only on the second build of a side,
    # once the opponent's average rating is known (see _play_match).
    plan = None
    if with_talents and catalog is not None and config is not None:
        own_avg = sum(min(99, c.player.rating + card_rating_bonus(c)) for c, _ in pairs) / len(pairs) if pairs else 0
        plan = path_match_service.ptour_plan(
            pairs, catalog, config, formation=squad.formation, opponent_avg=opponent_avg, own_avg=own_avg,
            coach_country=chemistry_service.coach_country_of(coach),
            stadium_club=chemistry_service.stadium_club_of(home_stadium), chemistry_on=chemistry_rules is not None,
        )
    chemistry = (
        chemistry_service.compute_chemistry(
            pairs, squad.formation, chemistry_rules, slot_count=len(formation_slots),
            coach_country=chemistry_service.coach_country_of(coach),
            # «Домашний стадион» — like the stadium boost, home side only.
            stadium_club=chemistry_service.stadium_club_of(home_stadium),
            **(plan.chemistry_hooks() if plan is not None else {}),
        )
        if chemistry_rules is not None else None
    )
    engine_pairs = override_positions(pairs, plan) if plan is not None else pairs
    with_slots: list[tuple[_EngineCard, FormationSlot]] = [
        (
            _engine_card(
                c, config, chemistry.rating_bonus(slot.code) if chemistry is not None else 0,
                talent=plan.talents.get(c.id) if plan is not None else None,
                talent_bonus=plan.static.get(c.id, 0) if plan is not None else 0,
            ),
            slot,
        )
        for c, slot in engine_pairs
    ]
    stadium_multiplier = (
        1.0 + float(squad.user_stadium_card.stadium.boost_pct) if is_home and squad.user_stadium_card else 1.0
    )
    side = build_side(with_slots, squad.mentality, squad.playstyle, coach=coach, stadium_multiplier=stadium_multiplier)
    lineup = [
        {
            "club_card_id": c.id, "player_id": c.player_id, "name": c.player.display_name,
            "rating": c.player.rating, "position": c.player.position.value, "category": slot.category,
            **({"skill": c.skill} if c.skill else {}),
            **({"talent": c.talent} if c.talent else {}),
        }
        for c, slot in with_slots
    ]
    chemistry_snapshot = None
    if chemistry is not None:
        chemistry_snapshot = {
            "team": chemistry.team, "max": chemistry.team_max,
            "cards": {str(c.id): chemistry.players[slot.code].points for c, slot in with_slots},
        }
    path_cards = [c.id for c, _ in pairs if path_service.is_path_card(c)]
    talented = catalog is not None and config is not None and any(
        path_match_service.talent_snapshot(c, catalog, config, "ptour") for c, _ in pairs if path_service.is_path_card(c)
    )
    return _Side(
        side=side, lineup=lineup, chemistry=chemistry_snapshot, path_cards=path_cards, talented=talented,
        talents=plan.snapshot() if plan is not None and plan.active else None,
    )


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
    chemistry_rules: ChemistryRules | None = None,
) -> tuple[int, int, list, dict | None]:
    """Returns (score_a, score_b, event_log, skill_snapshot). The snapshot is
    taken from the squads at this exact moment — the whole match is simulated
    in this one call, so nothing can change it mid-match; it is stored on the
    match row so the applied skills stay auditable after cards change."""
    catalog = await path_service.load_catalog(db) if config is not None and config.path_enabled else None
    side_a = await _build_side(db, user_a_id, is_home=True, config=config, chemistry_rules=chemistry_rules, catalog=catalog)
    side_b = await _build_side(db, user_b_id, is_home=False, config=config, chemistry_rules=chemistry_rules, catalog=catalog)
    if side_a is not None and side_b is not None and (side_a.talented or side_b.talented):
        # Rebuild the side(s) with talents, each against the other's plain
        # average rating («Большие матчи»).
        avg_a, avg_b = side_a.avg_rating, side_b.avg_rating
        if side_a.talented:
            side_a = await _build_side(
                db, user_a_id, is_home=True, config=config, chemistry_rules=chemistry_rules, catalog=catalog,
                opponent_avg=avg_b, with_talents=True,
            )
        if side_b.talented:
            side_b = await _build_side(
                db, user_b_id, is_home=False, config=config, chemistry_rules=chemistry_rules, catalog=catalog,
                opponent_avg=avg_a, with_talents=True,
            )
    if side_a is not None and side_b is not None:
        result = tournament_match_engine.simulate_match(
            side_a.side, side_b.side, side_a.lineup, side_b.lineup, config, names[user_a_id], names[user_b_id],
        )
        snapshot_a, snapshot_b = side_a.skill_snapshot(), side_b.skill_snapshot()
        snapshot = {"version": SNAPSHOT_VERSION, "a": snapshot_a, "b": snapshot_b} if snapshot_a or snapshot_b else None
        if side_a.chemistry is not None or side_b.chemistry is not None:
            # Rides along in the same frozen-at-simulation snapshot column so
            # the chemistry a round was played with stays auditable after the
            # squads (or the GameConfig tuning) change.
            snapshot = snapshot or {"version": SNAPSHOT_VERSION, "a": {}, "b": {}}
            snapshot["chemistry"] = {"a": side_a.chemistry, "b": side_b.chemistry}
        if side_a.path_cards or side_b.path_cards:
            # «Начало пути»: which path cards played (experience after the
            # match) and the talents applied — auditable like the skills.
            snapshot = snapshot or {"version": SNAPSHOT_VERSION, "a": {}, "b": {}}
            snapshot["path"] = {
                "cards": {"a": side_a.path_cards or [], "b": side_b.path_cards or []},
                "talents": {"a": side_a.talents, "b": side_b.talents},
            }
        return result.score_a, result.score_b, result.event_log, snapshot
    if side_a is None and side_b is None:
        return 0, 0, [], None
    return (0, 3, [], None) if side_a is None else (3, 0, [], None)


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
                score_a, score_b, event_log, skill_snapshot = await _play_match(
                    db, user_a_id, user_b_id, names, config,
                    chemistry_rules=chemistry_service.rules_from_dict(tournament.chemistry_rules),
                )
                match = PlayerTournamentMatch(
                    tournament_id=tournament.id, round_number=round_number, user_a_id=user_a_id, user_b_id=user_b_id,
                    score_a=score_a, score_b=score_b, event_log=event_log, simulated_at=datetime.now(timezone.utc),
                    skill_snapshot=skill_snapshot,
                )
                db.add(match)
                apply_match_result(standings[user_a_id], standings[user_b_id], score_a, score_b)

                # «Начало пути»: experience for the path cards that played
                # (own daily cap per card, never Arena attempts). Idempotent
                # per (card, match).
                path_cards = ((skill_snapshot or {}).get("path") or {}).get("cards") or {}
                for uid, side, own, opp in ((user_a_id, "a", score_a, score_b), (user_b_id, "b", score_b, score_a)):
                    if path_cards.get(side):
                        await path_match_service.award_side(
                            db, user_id=uid, source_type="ptour",
                            source_id=f"{tournament.id}:{round_number}:{user_a_id}:{user_b_id}",
                            card_ids=path_cards[side], own=own, opp=opp, event_log=event_log, side=side, config=config,
                        )

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
        await card_skill_service.grant_place_tokens(db, user, tournament.id, rank, config)
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
