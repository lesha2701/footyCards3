"""«Трофейная комната» клуба: everything the club has won, read from the
tables that already record it — league seasons (club_season_results),
weekly league podiums (club_league_results), club tournaments
(tournament_club_results), completed weekly quests and club wars. Public:
any player may look at any club's trophies."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.club import Club
from app.models.club_league import ClubLeagueResult, ClubSeasonResult
from app.models.club_quest import ClubQuestCompletion
from app.models.tournament import Tournament
from app.models.tournament_result import TournamentClubResult
from app.schemas.club_trophy import (
    ClubPodiumOut,
    ClubSeasonTrophyOut,
    ClubTournamentTrophyOut,
    ClubTrophiesOut,
)
from app.services.club_emblem_service import emblem_out
from app.services.club_league_service import DIVISION_NAMES

RECENT = 10


async def get_trophies(db: AsyncSession, club_id: int) -> ClubTrophiesOut:
    club = await db.get(Club, club_id)
    if club is None:
        raise NotFoundError("Клуб не найден")

    seasons = (await db.execute(
        select(ClubSeasonResult).where(ClubSeasonResult.club_id == club_id)
        .order_by(ClubSeasonResult.season_end_week.desc()).limit(RECENT * 2)
    )).scalars().all()
    podium_counts = dict((await db.execute(
        select(ClubLeagueResult.rank, func.count(ClubLeagueResult.id))
        .where(ClubLeagueResult.club_id == club_id, ClubLeagueResult.rank <= 3)
        .group_by(ClubLeagueResult.rank)
    )).all())
    recent_podiums = (await db.execute(
        select(ClubLeagueResult).where(ClubLeagueResult.club_id == club_id, ClubLeagueResult.rank <= 3)
        .order_by(ClubLeagueResult.week_start.desc()).limit(RECENT)
    )).scalars().all()
    tournaments = (await db.execute(
        select(TournamentClubResult, Tournament.created_at)
        .join(Tournament, Tournament.id == TournamentClubResult.tournament_id)
        .where(TournamentClubResult.club_id == club_id)
        .order_by(Tournament.created_at.desc())
    )).all()
    quests_completed = (await db.execute(
        select(func.count(ClubQuestCompletion.id)).where(ClubQuestCompletion.club_id == club_id)
    )).scalar_one()
    wars_won = wars_played = 0
    try:
        from app.services.club_war_service import war_record

        wars_won, wars_played = await war_record(db, club_id)
    except ImportError:  # wars not shipped yet
        pass

    return ClubTrophiesOut(
        club_id=club.id, name=club.name, logo_shape=club.logo_shape, logo_color=club.logo_color, emblem=emblem_out(club),
        division=club.league_division, division_name=DIVISION_NAMES[club.league_division],
        cups_count=club.cups_count, stars_count=club.stars_count, founded_at=club.founded_at,
        seasons=[
            ClubSeasonTrophyOut(
                season_end_week=s.season_end_week, division=s.division, division_name=DIVISION_NAMES[s.division],
                rank=s.rank, points=s.points, moved=s.moved,
            )
            for s in seasons
        ],
        league_gold=int(podium_counts.get(1, 0)), league_silver=int(podium_counts.get(2, 0)),
        league_bronze=int(podium_counts.get(3, 0)),
        recent_podiums=[
            ClubPodiumOut(week_start=r.week_start, division=r.division, division_name=DIVISION_NAMES[r.division], rank=r.rank, points=r.points)
            for r in recent_podiums
        ],
        tournaments_played=len(tournaments),
        tournaments_won=sum(1 for r, _ in tournaments if r.cup_awarded),
        best_tournament_rank=min((r.final_rank for r, _ in tournaments), default=None),
        recent_tournaments=[
            ClubTournamentTrophyOut(tournament_id=r.tournament_id, final_rank=r.final_rank, cup=r.cup_awarded, played_at=at)
            for r, at in tournaments[:RECENT]
        ],
        quests_completed=quests_completed,
        wars_played=wars_played, wars_won=wars_won,
    )
