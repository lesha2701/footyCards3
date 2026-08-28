from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.club import Club
from app.models.enums import TournamentStatus
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_match import TournamentMatch
from app.models.tournament_queue import TournamentQueueEntry, TournamentQueueState
from app.models.tournament_result import TournamentClubResult
from app.models.tournament_standing import TournamentClubStanding
from app.models.user import User
from app.schemas.club import ClubCreate, ClubDetailOut, ClubJoinRequestOut, ClubSummaryOut, JoinByInviteIn, TransferCaptainIn
from app.schemas.club_ranking import ClubRankingMetric, ClubRankingOut
from app.schemas.club_pack import ClubPackOut
from app.schemas.club_pack_open import ClubPackOpenResult, OpenClubPackRequest
from app.schemas.club_squad import ClubCardOut, ClubLineupOut, ClubLineupSetRequest
from app.schemas.tournament import (
    TournamentApplyResult,
    TournamentCurrentOut,
    TournamentDetailOut,
    TournamentMatchDetailOut,
    TournamentMatchSummaryOut,
    TournamentStandingOut,
)
from app.services import (
    club_pack_service,
    club_ranking_service,
    club_service,
    club_squad_service,
    tournament_match_engine,
    tournament_queue_service,
)
from app.services.tournament_standing_service import rank_standings

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("", response_model=list[ClubSummaryOut])
async def list_clubs(
    search: Optional[str] = Query(default=None), db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)
):
    return await club_service.list_clubs(db, search)


@router.get("/packs", response_model=list[ClubPackOut])
async def list_club_packs(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await club_pack_service.list_club_packs(db)


@router.get("/leaderboard", response_model=ClubRankingOut)
async def get_club_leaderboard(
    metric: ClubRankingMetric, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await club_ranking_service.get_club_ranking(db, metric, current_user_id=user.id)


@router.get("/me", response_model=ClubDetailOut)
async def get_my_club(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.get_my_club_detail(db, user)


@router.get("/{club_id}", response_model=ClubDetailOut)
async def get_club(club_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.get_club_detail(db, club_id, requester_user_id=user.id)


@router.post("", response_model=ClubDetailOut)
async def create_club(
    payload: ClubCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await club_service.create_club(db, user, payload)


@router.post("/{club_id}/join", response_model=ClubDetailOut)
async def join_club(club_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.join_open_club(db, user, club_id)


@router.post("/{club_id}/join-requests", response_model=ClubJoinRequestOut)
async def create_join_request(club_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.create_join_request(db, user, club_id)


@router.get("/me/join-requests", response_model=list[ClubJoinRequestOut])
async def list_join_requests(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.list_join_requests(db, user)


@router.post("/me/join-requests/{request_id}/accept", response_model=ClubDetailOut)
async def accept_join_request(request_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await club_service.respond_to_join_request(db, user, request_id, accept=True)
    return await club_service.get_my_club_detail(db, user)


@router.post("/me/join-requests/{request_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_join_request(request_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await club_service.respond_to_join_request(db, user, request_id, accept=False)


@router.post("/join-by-invite", response_model=ClubDetailOut)
async def join_by_invite(payload: JoinByInviteIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.join_by_invite(db, user, payload.invite_code)


@router.post("/me/leave", status_code=status.HTTP_200_OK)
async def leave_club(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await club_service.leave_club(db, user)
    return {"ok": True}


@router.post("/me/members/{user_id}/kick", response_model=ClubDetailOut)
async def kick_member(user_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.kick_member(db, user, user_id)


@router.post("/me/assistants/{user_id}/appoint", response_model=ClubDetailOut)
async def appoint_assistant(user_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.appoint_assistant(db, user, user_id)


@router.post("/me/assistants/{user_id}/remove", response_model=ClubDetailOut)
async def remove_assistant(user_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.remove_assistant(db, user, user_id)


@router.post("/me/transfer-captain", response_model=ClubDetailOut)
async def transfer_captain(payload: TransferCaptainIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.transfer_captain(db, user, payload.user_id)


@router.post("/me/disband", status_code=status.HTTP_204_NO_CONTENT)
async def disband_club(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await club_service.disband_club(db, user)


@router.post("/me/daily-claim", response_model=ClubDetailOut)
async def claim_daily_reward(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.claim_daily_reward(db, user)


@router.get("/me/lineup", response_model=ClubLineupOut)
async def get_club_lineup(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_squad_service.get_club_lineup(db, user)


@router.put("/me/lineup", response_model=ClubLineupOut)
async def set_club_lineup(payload: ClubLineupSetRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_squad_service.set_club_lineup(db, user, payload)


@router.get("/me/cards", response_model=list[ClubCardOut])
async def list_club_cards(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_squad_service.list_club_cards(db, user)


@router.post("/me/packs/{club_pack_id}/open", response_model=ClubPackOpenResult)
async def open_club_pack(club_pack_id: int, payload: OpenClubPackRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"open_club_pack:{user.id}", max_calls=10, window_seconds=60)
    return await club_pack_service.open_club_pack(db, user, club_pack_id, payload.idempotency_key)


@router.post("/tournament/apply", response_model=TournamentApplyResult)
async def apply_to_tournament(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await tournament_queue_service.apply_to_tournament(db, user)


@router.get("/tournament/current", response_model=TournamentCurrentOut)
async def get_current_tournament(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.services.club_service import _require_membership

    membership = await _require_membership(db, user.id)
    club_id = membership.club_id

    active_tc = (
        await db.execute(
            select(TournamentClub).join(Tournament, Tournament.id == TournamentClub.tournament_id)
            .where(TournamentClub.club_id == club_id, Tournament.status == "active")
        )
    ).scalar_one_or_none()
    if active_tc is not None:
        return TournamentCurrentOut(status="active", tournament_id=active_tc.tournament_id)

    # Scoped to the currently-open queue only — mirrors tournament_queue_service's
    # _is_already_queued. TournamentQueueEntry rows are never deleted once a queue forms
    # (entries from past, already-`formed` queues stay as history), so an unscoped lookup by
    # club_id alone would both misreport "queued" for a club whose old queue already formed
    # and crash on scalar_one_or_none() once a club has 2+ historical entries across past
    # queues. A club can only ever have at most one entry in the *current* open queue (Task 9
    # already prevents re-applying while still queued/active), so this scoped lookup is safe
    # with scalar_one_or_none().
    state = (await db.execute(select(TournamentQueueState).where(TournamentQueueState.id == 1))).scalar_one_or_none()
    if state is not None:
        queue_entry = (
            await db.execute(
                select(TournamentQueueEntry).where(
                    TournamentQueueEntry.club_id == club_id, TournamentQueueEntry.queue_id == state.current_queue_id
                )
            )
        ).scalar_one_or_none()
        if queue_entry is not None:
            position = (
                await db.execute(
                    select(func.count(TournamentQueueEntry.id))
                    .where(TournamentQueueEntry.queue_id == queue_entry.queue_id, TournamentQueueEntry.joined_at <= queue_entry.joined_at)
                )
            ).scalar_one()
            return TournamentCurrentOut(status="queued", queue_position=position)

    completed_tc = (
        await db.execute(
            select(TournamentClub).join(Tournament, Tournament.id == TournamentClub.tournament_id)
            .where(TournamentClub.club_id == club_id, Tournament.status == TournamentStatus.completed)
            .order_by(Tournament.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if completed_tc is not None:
        return TournamentCurrentOut(status="completed", tournament_id=completed_tc.tournament_id)

    return TournamentCurrentOut(status="not_queued")


@router.get("/tournament/{tournament_id}", response_model=TournamentDetailOut)
async def get_tournament_detail(tournament_id: int, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    tournament = await db.get(Tournament, tournament_id)
    if tournament is None:
        raise NotFoundError("Турнир не найден")

    standings = (await db.execute(select(TournamentClubStanding).where(TournamentClubStanding.tournament_id == tournament_id))).scalars().all()
    matches = (await db.execute(select(TournamentMatch).where(TournamentMatch.tournament_id == tournament_id))).scalars().all()
    ranked = rank_standings(standings, matches)

    club_names = {c.id: c.name for c in (await db.execute(select(Club).where(Club.id.in_([s.club_id for s in standings])))).scalars().all()}

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
            TournamentMatchSummaryOut(id=m.id, round_number=m.round_number, club_a_id=m.club_a_id, club_b_id=m.club_b_id, score_a=m.score_a, score_b=m.score_b)
            for m in matches
        ],
    )


@router.get("/tournament/{tournament_id}/matches/{match_id}", response_model=TournamentMatchDetailOut)
async def get_tournament_match_detail(
    tournament_id: int, match_id: int, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)
):
    match = await db.get(TournamentMatch, match_id)
    if match is None or match.tournament_id != tournament_id:
        raise NotFoundError("Матч не найден")

    event_log = match.event_log
    if any("description" not in event for event in event_log):
        club_names = {
            c.id: c.name
            for c in (await db.execute(select(Club).where(Club.id.in_([match.club_a_id, match.club_b_id])))).scalars().all()
        }
        club_a_name, club_b_name = club_names.get(match.club_a_id, ""), club_names.get(match.club_b_id, "")
        event_log = [
            event if "description" in event
            else {**event, "description": tournament_match_engine._describe_event(event["event_type"], event["team"], club_a_name, club_b_name)}
            for event in event_log
        ]

    return TournamentMatchDetailOut(
        id=match.id, round_number=match.round_number, club_a_id=match.club_a_id, club_b_id=match.club_b_id,
        score_a=match.score_a, score_b=match.score_b, event_log=event_log,
    )
