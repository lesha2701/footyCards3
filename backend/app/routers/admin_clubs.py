from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.club import Club, ClubMember
from app.models.club_budget import ClubBudgetTransaction
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_result import TournamentClubResult
from app.models.tournament_standing import TournamentClubStanding
from app.models.user import User
from app.schemas.admin_clubs import (
    AdminClubBudgetTransactionOut,
    AdminClubDetailOut,
    AdminClubMemberOut,
    AdminClubSummaryOut,
    AdminClubTournamentOut,
)

router = APIRouter(prefix="/admin/clubs", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=Page[AdminClubSummaryOut])
async def list_clubs(search: Optional[str] = None, params: PageParams = Depends(), db: AsyncSession = Depends(get_db)):
    member_count_subq = (
        select(ClubMember.club_id, func.count(ClubMember.id).label("cnt"))
        .group_by(ClubMember.club_id)
        .subquery()
    )
    query = (
        select(Club, func.coalesce(member_count_subq.c.cnt, 0))
        .outerjoin(member_count_subq, member_count_subq.c.club_id == Club.id)
    )
    count_query = select(func.count(Club.id))
    if search:
        pattern = f"%{search}%"
        query = query.where(Club.name.ilike(pattern))
        count_query = count_query.where(Club.name.ilike(pattern))

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(Club.founded_at.desc()).offset(params.offset).limit(params.page_size)
    rows = (await db.execute(query)).all()
    items = [
        AdminClubSummaryOut(
            id=c.id, name=c.name, club_type=c.club_type, logo_shape=c.logo_shape, logo_color=c.logo_color,
            captain_id=c.captain_id, member_count=count, budget=c.budget, cups_count=c.cups_count,
            stars_count=c.stars_count, founded_at=c.founded_at, is_disbanded=c.is_disbanded,
        )
        for c, count in rows
    ]
    return Page.build(items, total, params)


async def _get_club_or_404(db: AsyncSession, club_id: int) -> Club:
    club = await db.get(Club, club_id)
    if club is None:
        raise NotFoundError("Club not found")
    return club


async def _member_count(db: AsyncSession, club_id: int) -> int:
    return (await db.execute(select(func.count(ClubMember.id)).where(ClubMember.club_id == club_id))).scalar_one()


@router.get("/{club_id}", response_model=AdminClubDetailOut)
async def get_club(club_id: int, db: AsyncSession = Depends(get_db)):
    club = await _get_club_or_404(db, club_id)
    count = await _member_count(db, club_id)
    return AdminClubDetailOut(
        id=club.id, name=club.name, club_type=club.club_type, logo_shape=club.logo_shape, logo_color=club.logo_color,
        captain_id=club.captain_id, member_count=count, budget=club.budget, cups_count=club.cups_count,
        stars_count=club.stars_count, founded_at=club.founded_at, is_disbanded=club.is_disbanded,
        description=club.description, invite_code=club.invite_code,
        last_tournament_applied_at=club.last_tournament_applied_at,
    )


@router.get("/{club_id}/members", response_model=list[AdminClubMemberOut])
async def get_club_members(club_id: int, db: AsyncSession = Depends(get_db)):
    await _get_club_or_404(db, club_id)
    rows = (
        await db.execute(
            select(ClubMember, User)
            .join(User, User.id == ClubMember.user_id)
            .where(ClubMember.club_id == club_id)
            .order_by(ClubMember.joined_at)
        )
    ).all()
    return [
        AdminClubMemberOut(user_id=u.id, username=u.username, first_name=u.first_name, role=m.role, joined_at=m.joined_at)
        for m, u in rows
    ]


@router.get("/{club_id}/budget-transactions", response_model=Page[AdminClubBudgetTransactionOut])
async def get_club_budget_transactions(club_id: int, params: PageParams = Depends(), db: AsyncSession = Depends(get_db)):
    await _get_club_or_404(db, club_id)
    total = (
        await db.execute(select(func.count(ClubBudgetTransaction.id)).where(ClubBudgetTransaction.club_id == club_id))
    ).scalar_one()
    result = await db.execute(
        select(ClubBudgetTransaction)
        .where(ClubBudgetTransaction.club_id == club_id)
        .order_by(ClubBudgetTransaction.created_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    items = [AdminClubBudgetTransactionOut.model_validate(t) for t in result.scalars().all()]
    return Page.build(items, total, params)


@router.get("/{club_id}/tournaments", response_model=list[AdminClubTournamentOut])
async def get_club_tournaments(club_id: int, db: AsyncSession = Depends(get_db)):
    await _get_club_or_404(db, club_id)
    rows = (
        await db.execute(
            select(TournamentClub, Tournament, TournamentClubStanding)
            .join(Tournament, Tournament.id == TournamentClub.tournament_id)
            .join(
                TournamentClubStanding,
                (TournamentClubStanding.tournament_id == TournamentClub.tournament_id)
                & (TournamentClubStanding.club_id == TournamentClub.club_id),
            )
            .where(TournamentClub.club_id == club_id)
            .order_by(Tournament.id.desc())
        )
    ).all()

    tournament_ids = [t.id for _, t, _ in rows]
    results_by_tournament: dict[int, TournamentClubResult] = {}
    if tournament_ids:
        result_rows = (
            await db.execute(
                select(TournamentClubResult).where(
                    TournamentClubResult.club_id == club_id, TournamentClubResult.tournament_id.in_(tournament_ids)
                )
            )
        ).scalars().all()
        results_by_tournament = {r.tournament_id: r for r in result_rows}

    return [
        AdminClubTournamentOut(
            tournament_id=t.id, status=t.status, rounds_simulated=t.rounds_simulated,
            points=s.points, goals_for=s.goals_for, goals_against=s.goals_against,
            final_rank=results_by_tournament[t.id].final_rank if t.id in results_by_tournament else None,
            budget_awarded=results_by_tournament[t.id].budget_awarded if t.id in results_by_tournament else None,
            stars_delta=results_by_tournament[t.id].stars_delta if t.id in results_by_tournament else None,
            cup_awarded=results_by_tournament[t.id].cup_awarded if t.id in results_by_tournament else None,
        )
        for _, t, s in rows
    ]
