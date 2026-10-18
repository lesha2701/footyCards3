"""«Лига клубов»: a weekly table of clubs ranked by their members' activity.

Points are not stored per event — they are derived on read from the tables
that already record the activity, so no game/pack/task service needs a hook:

- a finished mini-game session, Arena match, penalty duel or Tactico match
  → `club_league_points_game` (both humans of a PvP duel score);
- a pack bought for coins (`PackOpening.price_paid > 0`) or for Stars
  (a completed `StarsInvoice` with a pack) → `club_league_points_pack`;
- a completed task → `club_league_points_task`.

Only activity after the member joined the club counts, and each member's
weekly contribution is capped (`club_league_member_weekly_cap`) so a single
grinder cannot carry a club. Weeks run Monday 00:00 → Monday 00:00 in the
app timezone.

Settlement has no scheduler of its own: `settle_due` pays out the previous
week the first time anyone opens the league after Monday 00:00, and the bot
also pings `/internal/clubs/league/settle` at its career slots. The
`club_league_weeks` primary key makes a second, concurrent settlement of the
same week roll back instead of paying twice.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import app_timezone, local_today
from app.models.club import Club, ClubMember
from app.models.club_league import ClubLeagueResult, ClubLeagueWeek
from app.models.enums import (
    ClubBudgetTransactionType,
    GameSessionStatus,
    MatchStatus,
    NotificationType,
    PenaltyMatchStatus,
    TacticoMatchStatus,
)
from app.models.game import GameSession
from app.models.match import Match
from app.models.pack import PackOpening, StarsInvoice
from app.models.penalty import PenaltyMatch
from app.models.tactico import TacticoMatch
from app.models.task import UserTask
from app.models.user import User
from app.schemas.club_league import (
    ClubLeagueLastWeekOut,
    ClubLeagueMemberOut,
    ClubLeagueOut,
    ClubLeagueRowOut,
)
from app.services.club_budget_service import credit_club_budget
from app.services.club_emblem_service import emblem_out
from app.services.club_service import _get_membership, _lock_club
from app.services.game_config_service import get_config
from app.services.notification_service import notify

TABLE_SIZE = 20
PODIUM_SIZE = 3


def week_start_for(now: Optional[datetime] = None) -> date:
    today = local_today(now)
    return today - timedelta(days=today.weekday())


def week_bounds(week_start: date) -> tuple[datetime, datetime]:
    """[start, end) of the league week in UTC."""
    start = datetime.combine(week_start, time.min, tzinfo=app_timezone()).astimezone(timezone.utc)
    end = datetime.combine(week_start + timedelta(days=7), time.min, tzinfo=app_timezone()).astimezone(timezone.utc)
    return start, end


@dataclass
class _Tally:
    games: int = 0
    packs: int = 0
    tasks: int = 0


@dataclass
class _ClubTally:
    club_id: int
    points: int = 0
    members: dict[int, int] = field(default_factory=dict)


async def _activity(
    db: AsyncSession, start: datetime, end: datetime, club_id: Optional[int] = None,
) -> dict[tuple[int, int], _Tally]:
    """(club_id, user_id) -> counts for every member of every active club
    (or of one club) with activity in [start, end) after they joined."""
    tallies: dict[tuple[int, int], _Tally] = {}

    async def add(kind: str, user_col, ts_col, *conditions) -> None:
        query = (
            select(ClubMember.club_id, ClubMember.user_id, func.count())
            .select_from(ClubMember)
            .join(Club, Club.id == ClubMember.club_id)
            .join(ts_col.class_, user_col == ClubMember.user_id)
            .where(
                Club.is_disbanded.is_(False),
                ts_col >= start, ts_col < end, ts_col >= ClubMember.joined_at,
                *conditions,
            )
            .group_by(ClubMember.club_id, ClubMember.user_id)
        )
        if club_id is not None:
            query = query.where(ClubMember.club_id == club_id)
        for cid, uid, count in (await db.execute(query)).all():
            tally = tallies.setdefault((cid, uid), _Tally())
            setattr(tally, kind, getattr(tally, kind) + count)

    finished_session = GameSession.status.in_([GameSessionStatus.won, GameSessionStatus.lost, GameSessionStatus.rewarded])
    await add("games", GameSession.user_id, GameSession.created_at, finished_session)
    await add("games", Match.user_id, Match.created_at, Match.status == MatchStatus.finished)
    for user_col in (PenaltyMatch.user_id, PenaltyMatch.opponent_user_id):
        await add("games", user_col, PenaltyMatch.resolved_at, PenaltyMatch.status == PenaltyMatchStatus.finished)
    for user_col in (TacticoMatch.user_id, TacticoMatch.opponent_user_id):
        await add("games", user_col, TacticoMatch.resolved_at, TacticoMatch.status == TacticoMatchStatus.finished)
    await add("packs", PackOpening.user_id, PackOpening.created_at, PackOpening.price_paid > 0)
    await add("packs", StarsInvoice.user_id, StarsInvoice.completed_at, StarsInvoice.pack_id.is_not(None))
    await add("tasks", UserTask.user_id, UserTask.completed_at)
    return tallies


def _member_points(tally: _Tally, config) -> int:
    raw = (
        tally.games * config.club_league_points_game
        + tally.packs * config.club_league_points_pack
        + tally.tasks * config.club_league_points_task
    )
    return min(raw, config.club_league_member_weekly_cap)


async def compute_table(db: AsyncSession, week_start: date, config) -> list[_ClubTally]:
    """Clubs with points > 0, best first (ties: older club first)."""
    start, end = week_bounds(week_start)
    clubs: dict[int, _ClubTally] = {}
    for (cid, uid), tally in (await _activity(db, start, end)).items():
        points = _member_points(tally, config)
        club = clubs.setdefault(cid, _ClubTally(club_id=cid))
        club.points += points
        club.members[uid] = points
    return sorted((c for c in clubs.values() if c.points > 0), key=lambda c: (-c.points, c.club_id))


def _reward_for(rank: int, config) -> int:
    rewards = config.club_league_rewards or []
    return max(0, int(rewards[rank - 1])) if rank <= len(rewards) else 0


async def settle_due(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """Settles the previous week if nobody has yet. Returns the number of
    clubs that received a reward (0 when there was nothing to do). Commits
    on its own, so call it before making any other changes in the session."""
    config = await get_config(db)
    if not config.club_league_enabled:
        return 0
    week = week_start_for(now) - timedelta(days=7)
    if await db.get(ClubLeagueWeek, week) is not None:
        return 0
    # The first week the league ever settles is only a marker: activity from
    # before the league existed is never paid out.
    bootstrap = (await db.execute(select(ClubLeagueWeek.week_start).limit(1))).scalar_one_or_none() is None
    try:
        db.add(ClubLeagueWeek(week_start=week, is_bootstrap=bootstrap))
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return 0
    if bootstrap:
        await db.commit()
        return 0

    rewarded = 0
    for rank, row in enumerate(await compute_table(db, week, config), start=1):
        reward = _reward_for(rank, config)
        db.add(ClubLeagueResult(week_start=week, club_id=row.club_id, rank=rank, points=row.points, reward=reward))
        if reward <= 0:
            continue
        club = await _lock_club(db, row.club_id)
        await credit_club_budget(
            db, club, reward, ClubBudgetTransactionType.league_reward,
            f"Лига клубов: {rank} место ({week.strftime('%d.%m')})", related_object_type="club_league_week",
        )
        member_ids = (await db.execute(select(ClubMember.user_id).where(ClubMember.club_id == row.club_id))).scalars().all()
        for uid in member_ids:
            await notify(
                db, uid, NotificationType.club_league_reward, "Лига клубов: итоги недели",
                f"Клуб «{club.name}» занял {rank} место ({row.points} очк.) и получил {reward} монет в бюджет!",
                related_object_type="club", related_object_id=row.club_id,
            )
        rewarded += 1
    await db.commit()
    return rewarded


async def _rows(db: AsyncSession, entries: list[tuple[int, int, int, int]]) -> list[ClubLeagueRowOut]:
    """(rank, club_id, points, reward) -> rows with club name/emblem."""
    if not entries:
        return []
    ids = [cid for _, cid, _, _ in entries]
    clubs = {c.id: c for c in (await db.execute(select(Club).where(Club.id.in_(ids)))).scalars().all()}
    return [
        ClubLeagueRowOut(
            rank=rank, club_id=cid, name=clubs[cid].name, logo_shape=clubs[cid].logo_shape,
            logo_color=clubs[cid].logo_color, emblem=emblem_out(clubs[cid]), points=points, reward=reward,
        )
        for rank, cid, points, reward in entries
        if cid in clubs
    ]


async def _last_week(db: AsyncSession, week: date, my_club_id: Optional[int]) -> Optional[ClubLeagueLastWeekOut]:
    marker = await db.get(ClubLeagueWeek, week)
    if marker is None or marker.is_bootstrap:
        return None
    results = (
        await db.execute(
            select(ClubLeagueResult)
            .where(
                ClubLeagueResult.week_start == week,
                or_(ClubLeagueResult.rank <= PODIUM_SIZE, ClubLeagueResult.club_id == my_club_id),
            )
            .order_by(ClubLeagueResult.rank)
        )
    ).scalars().all()
    rows = await _rows(db, [(r.rank, r.club_id, r.points, r.reward) for r in results])
    mine = next((r for r in rows if r.club_id == my_club_id), None)
    return ClubLeagueLastWeekOut(week_start=week, podium=[r for r in rows if r.rank <= PODIUM_SIZE], my_row=mine)


async def get_league(db: AsyncSession, user: User) -> ClubLeagueOut:
    await settle_due(db)
    config = await get_config(db)
    week = week_start_for()
    start, end = week_bounds(week)
    membership = await _get_membership(db, user.id)
    my_club_id = membership.club_id if membership else None

    table = await compute_table(db, week, config) if config.club_league_enabled else []
    ranked = [(rank, row) for rank, row in enumerate(table, start=1)]
    shown = [(rank, row.club_id, row.points, _reward_for(rank, config)) for rank, row in ranked[:TABLE_SIZE]]
    mine = next(((rank, row) for rank, row in ranked if row.club_id == my_club_id), None)
    if mine and mine[0] > TABLE_SIZE:
        shown.append((mine[0], mine[1].club_id, mine[1].points, _reward_for(mine[0], config)))
    rows = await _rows(db, shown)

    members: list[ClubLeagueMemberOut] = []
    if my_club_id is not None:
        tallies = await _activity(db, start, end, club_id=my_club_id)
        member_rows = (
            await db.execute(
                select(User).join(ClubMember, ClubMember.user_id == User.id).where(ClubMember.club_id == my_club_id)
            )
        ).scalars().all()
        for member in member_rows:
            tally = tallies.get((my_club_id, member.id), _Tally())
            members.append(
                ClubLeagueMemberOut(
                    user_id=member.id, name=member.username or member.first_name or f"#{member.id}",
                    games=tally.games, packs=tally.packs, tasks=tally.tasks, points=_member_points(tally, config),
                )
            )
        members.sort(key=lambda m: (-m.points, m.user_id))

    return ClubLeagueOut(
        enabled=config.club_league_enabled,
        week_start=week, ends_at=end,
        points_game=config.club_league_points_game, points_pack=config.club_league_points_pack,
        points_task=config.club_league_points_task, member_weekly_cap=config.club_league_member_weekly_cap,
        rewards=[max(0, int(r)) for r in (config.club_league_rewards or [])],
        clubs_count=len(table),
        table=rows,
        my_row=next((r for r in rows if r.club_id == my_club_id), None),
        members=members,
        last_week=await _last_week(db, week - timedelta(days=7), my_club_id),
    )

