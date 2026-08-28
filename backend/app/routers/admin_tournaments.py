from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.club import Club
from app.models.enums import TournamentStatus
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_match import TournamentMatch
from app.models.tournament_result import TournamentClubResult
from app.models.tournament_standing import TournamentClubStanding
from app.schemas.admin_tournaments import AdminTournamentStatsOut, AdminTournamentSummaryOut
from app.schemas.tournament import TournamentDetailOut, TournamentMatchSummaryOut, TournamentStandingOut
from app.services.tournament_standing_service import rank_standings

router = APIRouter(prefix="/admin/tournaments", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("/stats", response_model=AdminTournamentStatsOut)
async def get_tournament_stats(db: AsyncSession = Depends(get_db)):
    active_count = (
        await db.execute(select(func.count(Tournament.id)).where(Tournament.status == TournamentStatus.active))
    ).scalar_one()
    completed_count = (
        await db.execute(select(func.count(Tournament.id)).where(Tournament.status == TournamentStatus.completed))
    ).scalar_one()
    return AdminTournamentStatsOut(active_count=active_count, completed_count=completed_count)


@router.get("", response_model=Page[AdminTournamentSummaryOut])
async def list_tournaments(
    status: Optional[TournamentStatus] = None, params: PageParams = Depends(), db: AsyncSession = Depends(get_db)
):
    club_count_subq = (
        select(TournamentClub.tournament_id, func.count(TournamentClub.id).label("cnt"))
        .group_by(TournamentClub.tournament_id)
        .subquery()
    )
    query = select(Tournament, func.coalesce(club_count_subq.c.cnt, 0)).outerjoin(
        club_count_subq, club_count_subq.c.tournament_id == Tournament.id
    )
    count_query = select(func.count(Tournament.id))
    if status is not None:
        query = query.where(Tournament.status == status)
        count_query = count_query.where(Tournament.status == status)

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(Tournament.id.desc()).offset(params.offset).limit(params.page_size)
    rows = (await db.execute(query)).all()
    items = [
        AdminTournamentSummaryOut(
            id=t.id, status=t.status, rounds_simulated=t.rounds_simulated, club_count=count, created_at=t.created_at,
        )
        for t, count in rows
    ]
    return Page.build(items, total, params)


@router.get("/{tournament_id}", response_model=TournamentDetailOut)
async def get_tournament_detail(tournament_id: int, db: AsyncSession = Depends(get_db)):
    tournament = await db.get(Tournament, tournament_id)
    if tournament is None:
        raise NotFoundError("Tournament not found")

    standings = (
        await db.execute(select(TournamentClubStanding).where(TournamentClubStanding.tournament_id == tournament_id))
    ).scalars().all()
    matches = (
        await db.execute(select(TournamentMatch).where(TournamentMatch.tournament_id == tournament_id))
    ).scalars().all()
    ranked = rank_standings(standings, matches)

    club_names = {
        c.id: c.name
        for c in (await db.execute(select(Club).where(Club.id.in_([s.club_id for s in standings])))).scalars().all()
    }

    results_by_club: dict[int, TournamentClubResult] = {}
    if tournament.status == TournamentStatus.completed:
        results = (
            await db.execute(select(TournamentClubResult).where(TournamentClubResult.tournament_id == tournament_id))
        ).scalars().all()
        results_by_club = {r.club_id: r for r in results}

    return TournamentDetailOut(
        id=tournament.id, status=tournament.status.value, rounds_simulated=tournament.rounds_simulated,
        standings=[
            TournamentStandingOut(
                club_id=s.club_id, club_name=club_names.get(s.club_id, ""), points=s.points,
                goals_for=s.goals_for, goals_against=s.goals_against, final_rank=index + 1,
                budget_awarded=results_by_club[s.club_id].budget_awarded if s.club_id in results_by_club else None,
                stars_delta=results_by_club[s.club_id].stars_delta if s.club_id in results_by_club else None,
                cup_awarded=results_by_club[s.club_id].cup_awarded if s.club_id in results_by_club else None,
            )
            for index, s in enumerate(ranked)
        ],
        matches=[
            TournamentMatchSummaryOut(
                id=m.id, round_number=m.round_number, club_a_id=m.club_a_id, club_b_id=m.club_b_id,
                score_a=m.score_a, score_b=m.score_b,
            )
            for m in matches
        ],
        # Admin view doesn't need the live simulation countdown that the player-facing
        # endpoint computes (app.routers.clubs._next_round_seconds_remaining) — it's a
        # private helper of that router and not worth coupling admin_tournaments to it.
        next_round_seconds_remaining=None,
    )
