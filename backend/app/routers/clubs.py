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
from app.schemas.club import (
    ClubCreate,
    ClubCreationCostOut,
    ClubDetailOut,
    ClubJoinRequestOut,
    ClubSummaryOut,
    ClubTypeUpdate,
    JoinByInviteIn,
    TransferCaptainIn,
)
from app.schemas.club_ranking import ClubRankingMetric, ClubRankingOut
from app.schemas.club_game import ClubGameClaimOut, ClubGameStartOut, ClubGameSubmitOut, ClubGameSubmitRequest
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
    club_game_service,
    club_pack_service,
    club_ranking_service,
    club_service,
    club_squad_service,
    tournament_match_engine,
    tournament_queue_service,
)
from app.services.game_config_service import get_config
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


@router.get("/creation-cost", response_model=ClubCreationCostOut)
async def get_club_creation_cost(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    config = await get_config(db)
    return ClubCreationCostOut(creation_cost_coins=config.club_creation_cost_coins)


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


@router.put("/me/type", response_model=ClubDetailOut)
async def update_club_type(payload: ClubTypeUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.update_club_type(db, user, payload.club_type)


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


@router.post("/me/game/start", response_model=ClubGameStartOut)
async def start_club_game(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"club_game_start:{user.id}", max_calls=20, window_seconds=60)
    return await club_game_service.start_session(db, user)


@router.post("/me/game/{session_id}/submit", response_model=ClubGameSubmitOut)
async def submit_club_game_round(
    session_id: int, payload: ClubGameSubmitRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await club_game_service.submit_round(db, user, session_id, payload.answer)


@router.post("/me/game/{session_id}/end", response_model=ClubGameSubmitOut)
async def end_club_game(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_game_service.end_session(db, user, session_id)


@router.post("/me/game/{session_id}/claim", response_model=ClubGameClaimOut)
async def claim_club_game_reward(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_game_service.claim_reward(db, user, session_id)


@router.post("/tournament/apply", response_model=TournamentApplyResult)
async def apply_to_tournament(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await tournament_queue_service.apply_to_tournament(db, user)


# Fixed daily times (local app timezone) the bot's scheduler fires a simulation round —
# keep in sync with bot/services/tournament_scheduler.py's SIMULATION_SLOTS.
_SIMULATION_SLOTS = [(12, 0), (20, 0)]


async def _next_round_seconds_remaining(db: AsyncSession, tournament: Tournament) -> Optional[int]:
    """Seconds until the next round fires, or 0 if one is already due. A slot's nominal time
    passing does NOT mean it has fired yet — the bot's sweep only polls every
    `LOOP_CHECK_INTERVAL_SECONDS` (15 min, see bot/services/tournament_scheduler.py), so there's
    a real catch-up window after each slot time. Naively jumping straight to "the next slot
    after this one" the instant the clock passes a slot time is actively misleading during that
    window — e.g. at 20:04 it would claim ~16h remaining (until tomorrow's 12:00 slot) even
    though the 20:00 round may simply not have been picked up by the sweep yet. Instead, check
    TournamentSimulationSlotLog — the bot's own dedup record of which slots have actually run —
    for the most recently passed slot; only advance past it once it's confirmed processed."""
    from datetime import datetime, timedelta

    from app.core.timeutil import app_timezone
    from app.models.tournament_simulation_slot_log import TournamentSimulationSlotLog

    if tournament.status != TournamentStatus.active or tournament.rounds_simulated >= 14:
        return None

    now = datetime.now(app_timezone())
    today_slots = [now.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in _SIMULATION_SLOTS]
    all_instants = sorted(today_slots + [t + timedelta(days=1) for t in today_slots] + [t - timedelta(days=1) for t in today_slots])
    upcoming = [t for t in all_instants if t > now]
    past = [t for t in all_instants if t <= now]

    if past:
        last_slot_key = past[-1].strftime("%Y-%m-%dT%H:%M")
        processed = (
            await db.execute(
                select(TournamentSimulationSlotLog.id).where(
                    TournamentSimulationSlotLog.kind == "simulate_round",
                    TournamentSimulationSlotLog.slot_key == last_slot_key,
                )
            )
        ).scalar_one_or_none()
        if processed is None:
            return 0

    return max(0, int((upcoming[0] - now).total_seconds()))


async def _cooldown_seconds_remaining(db: AsyncSession, club: Club) -> Optional[int]:
    """None once the club is free to submit a new tournament application; otherwise the
    seconds left in `config.club_tournament_cooldown_hours` since its last application,
    mirroring `tournament_queue_service.apply_to_tournament`'s own gating exactly."""
    if club.last_tournament_applied_at is None:
        return None
    config = await get_config(db)
    from datetime import datetime, timezone

    from app.core.timeutil import ensure_aware

    elapsed = (datetime.now(timezone.utc) - ensure_aware(club.last_tournament_applied_at)).total_seconds()
    remaining = config.club_tournament_cooldown_hours * 3600 - elapsed
    return max(0, int(remaining)) if remaining > 0 else None


@router.get("/tournament/current", response_model=TournamentCurrentOut)
async def get_current_tournament(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.services.club_service import _require_membership

    membership = await _require_membership(db, user.id)
    club_id = membership.club_id
    club = await db.get(Club, club_id)

    active_tc = (
        await db.execute(
            select(TournamentClub).join(Tournament, Tournament.id == TournamentClub.tournament_id)
            .where(TournamentClub.club_id == club_id, Tournament.status == "active")
        )
    ).scalar_one_or_none()
    if active_tc is not None:
        return TournamentCurrentOut(status="active", tournament_id=active_tc.tournament_id, can_apply=False)

    # can_apply/cooldown are computed once, up front, and reused across every branch below —
    # a club can be simultaneously "showing its last completed tournament" (status) and "free
    # to apply for a new one" (can_apply); these are independent facts about the club, not
    # mutually exclusive states, so the frontend needs both regardless of which status string
    # this endpoint returns.
    cooldown_seconds_remaining = await _cooldown_seconds_remaining(db, club)
    can_apply = cooldown_seconds_remaining is None

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
            return TournamentCurrentOut(status="queued", queue_position=position, can_apply=False)

    completed_tc = (
        await db.execute(
            select(TournamentClub).join(Tournament, Tournament.id == TournamentClub.tournament_id)
            .where(TournamentClub.club_id == club_id, Tournament.status == TournamentStatus.completed)
            .order_by(Tournament.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if completed_tc is not None:
        return TournamentCurrentOut(
            status="completed", tournament_id=completed_tc.tournament_id,
            can_apply=can_apply, cooldown_seconds_remaining=cooldown_seconds_remaining,
        )

    return TournamentCurrentOut(status="not_queued", can_apply=can_apply, cooldown_seconds_remaining=cooldown_seconds_remaining)


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
        next_round_seconds_remaining=await _next_round_seconds_remaining(db, tournament),
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
