from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.timeutil import app_timezone
from app.models.enums import TournamentStatus
from app.models.player_tournament import (
    PlayerTournament, PlayerTournamentMatch, PlayerTournamentResult, PlayerTournamentStanding,
)
from app.models.tournament_simulation_slot_log import TournamentSimulationSlotLog
from app.models.user import User
from app.schemas.player_tournament import (
    PlayerTournamentDetailOut, PlayerTournamentMatchDetailOut, PlayerTournamentMatchSummaryOut,
    PlayerTournamentStandingOut, TournamentRatingRowOut,
)
from app.services.player_tournament_fixture_service import SIMULATION_SLOTS, TOTAL_ROUNDS
from app.services.player_tournament_simulation_service import SLOT_KIND
from app.services.player_tournament_standing_service import rank_standings


async def next_round_seconds_remaining(db: AsyncSession, tournament: PlayerTournament) -> int | None:
    """Seconds until the next slot fires, or 0 when the last passed slot has
    not been processed yet (the bot polls every ~15 min, so there is a
    catch-up window after each slot time — same reasoning as
    routers/clubs._next_round_seconds_remaining)."""
    if tournament.status != TournamentStatus.active or tournament.rounds_simulated >= TOTAL_ROUNDS:
        return None

    now = datetime.now(app_timezone())
    today = [now.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in SIMULATION_SLOTS]
    instants = sorted(today + [t + timedelta(days=1) for t in today] + [t - timedelta(days=1) for t in today])
    past = [t for t in instants if t <= now]
    upcoming = [t for t in instants if t > now]

    if past:
        last_key = past[-1].strftime("%Y-%m-%dT%H:%M")
        processed = (
            await db.execute(
                select(TournamentSimulationSlotLog.id).where(
                    TournamentSimulationSlotLog.kind == SLOT_KIND, TournamentSimulationSlotLog.slot_key == last_key,
                )
            )
        ).scalar_one_or_none()
        if processed is None and (now - past[-1]) < timedelta(hours=6):
            return 0
    return max(0, int((upcoming[0] - now).total_seconds()))


async def get_tournament_detail(db: AsyncSession, tournament_id: int) -> PlayerTournamentDetailOut:
    tournament = await db.get(PlayerTournament, tournament_id)
    if tournament is None:
        raise NotFoundError("Турнир не найден")

    standings = (
        await db.execute(select(PlayerTournamentStanding).where(PlayerTournamentStanding.tournament_id == tournament_id)
            .order_by(PlayerTournamentStanding.user_id))
    ).scalars().all()
    matches = (
        await db.execute(
            select(PlayerTournamentMatch).where(PlayerTournamentMatch.tournament_id == tournament_id)
            .order_by(PlayerTournamentMatch.round_number, PlayerTournamentMatch.id)
        )
    ).scalars().all()
    users = {
        u.id: u for u in (await db.execute(select(User).where(User.id.in_([s.user_id for s in standings])))).scalars().all()
    }
    results = {
        r.user_id: r for r in (
            await db.execute(select(PlayerTournamentResult).where(PlayerTournamentResult.tournament_id == tournament_id))
        ).scalars().all()
    }

    ranked = rank_standings(list(standings), list(matches))
    if results:  # concluded: the persisted final_rank is authoritative
        ranked = sorted(ranked, key=lambda st: results[st.user_id].final_rank if st.user_id in results else 10**6)
    rows = []
    for s in ranked:
        result = results.get(s.user_id)
        rows.append(PlayerTournamentStandingOut(
            user_id=s.user_id, display_name=users[s.user_id].full_display_name(),
            points=s.points, goals_for=s.goals_for, goals_against=s.goals_against,
            final_rank=result.final_rank if result else None,
            coins_awarded=result.coins_awarded if result else None,
            rating_delta=result.rating_delta if result else None,
        ))
    return PlayerTournamentDetailOut(
        id=tournament.id, status=tournament.status.value, rounds_simulated=tournament.rounds_simulated,
        standings=rows,
        matches=[PlayerTournamentMatchSummaryOut(
            id=m.id, round_number=m.round_number, user_a_id=m.user_a_id, user_b_id=m.user_b_id,
            score_a=m.score_a, score_b=m.score_b,
        ) for m in matches],
        next_round_seconds_remaining=await next_round_seconds_remaining(db, tournament),
    )


async def get_match_detail(db: AsyncSession, match_id: int) -> PlayerTournamentMatchDetailOut:
    match = await db.get(PlayerTournamentMatch, match_id)
    if match is None:
        raise NotFoundError("Матч не найден")
    a = await db.get(User, match.user_a_id)
    b = await db.get(User, match.user_b_id)
    return PlayerTournamentMatchDetailOut(
        id=match.id, round_number=match.round_number, user_a_id=a.id, user_b_id=b.id,
        user_a_name=a.full_display_name(), user_b_name=b.full_display_name(),
        score_a=match.score_a, score_b=match.score_b, event_log=match.event_log,
    )


async def get_rating_leaderboard(db: AsyncSession, limit: int = 50) -> list[TournamentRatingRowOut]:
    users = (
        await db.execute(
            select(User).where(
                User.tournament_rating != 0, User.is_banned.is_(False), User.is_admin.is_(False)
            )
            .order_by(User.tournament_rating.desc(), User.id).limit(limit)
        )
    ).scalars().all()
    return [
        TournamentRatingRowOut(user_id=u.id, display_name=u.full_display_name(), tournament_rating=u.tournament_rating)
        for u in users
    ]
