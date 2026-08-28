from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import ensure_aware
from app.models.club import Club
from app.models.enums import ClubBudgetTransactionType, NotificationType, TournamentStatus
from app.models.tournament import Tournament
from app.models.tournament_result import TournamentClubResult
from app.models.tournament_standing import TournamentClubStanding
from app.services.club_budget_service import credit_club_budget
from app.services.game_config_service import get_config
from app.services.tournament_standing_service import rank_standings
from app.services import tournament_notification_service

_STARS_BY_RANK = {1: 3, 2: 2, 3: 1, 4: 0, 5: 0, 6: -1, 7: -2, 8: -3}


def _can_apply_now(club: Club, config) -> bool:
    """Mirrors app.routers.clubs._cooldown_seconds_remaining's own gating exactly (can_apply is
    None-cooldown), duplicated here rather than imported since routers must not be imported
    from services. A club's cooldown is measured from its *last application*, not from when its
    tournament concludes — by the time a 14-round tournament finishes (days), the cooldown has
    virtually always already elapsed, but this still checks properly rather than assuming."""
    if club.last_tournament_applied_at is None:
        return True
    elapsed = (datetime.now(timezone.utc) - ensure_aware(club.last_tournament_applied_at)).total_seconds()
    return elapsed >= config.club_tournament_cooldown_hours * 3600


async def conclude_tournament(
    db: AsyncSession, tournament: Tournament, standings: list[TournamentClubStanding], matches: list
) -> list[TournamentClubResult]:
    config = await get_config(db)
    budget_by_rank = {
        1: config.club_tournament_budget_place_1, 2: config.club_tournament_budget_place_2,
        3: config.club_tournament_budget_place_3, 4: config.club_tournament_budget_place_4,
        5: config.club_tournament_budget_place_5, 6: config.club_tournament_budget_place_6,
        7: config.club_tournament_budget_place_7, 8: config.club_tournament_budget_place_8,
    }

    ranked = rank_standings(standings, matches)
    results: list[TournamentClubResult] = []

    for index, standing in enumerate(ranked):
        rank = index + 1
        club = await db.get(Club, standing.club_id)
        stars_delta = _STARS_BY_RANK[rank]
        budget_awarded = budget_by_rank[rank]
        cup_awarded = rank == 1

        await credit_club_budget(
            db, club, budget_awarded, ClubBudgetTransactionType.tournament_reward,
            f"Награда за {rank}-е место в турнире #{tournament.id}",
            related_object_type="tournament", related_object_id=tournament.id,
        )
        club.stars_count += stars_delta
        if cup_awarded:
            club.cups_count += 1
        db.add(club)

        result = TournamentClubResult(
            tournament_id=tournament.id, club_id=club.id, final_rank=rank,
            budget_awarded=budget_awarded, stars_delta=stars_delta, cup_awarded=cup_awarded,
        )
        db.add(result)
        results.append(result)

        await tournament_notification_service.notify_club_members(
            db, club.id, NotificationType.club_tournament_results_ready,
            "Турнир завершён", f"Твой клуб занял {rank}-е место в турнире — загляни за результатами!",
        )
        if _can_apply_now(club, config):
            await tournament_notification_service.notify_club_managers(
                db, club.id, NotificationType.club_tournament_apply_available,
                "Можно подавать новую заявку",
                "Твой клуб уже может подать заявку на новый турнир!",
            )

    tournament.status = TournamentStatus.completed
    db.add(tournament)
    return results
