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
import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import app_timezone, local_today
from app.models.club import Club, ClubMember
from app.models.club_league import ClubLeagueResult, ClubLeagueWeek, ClubSeasonResult
from app.models.enums import (
    ClubBudgetTransactionType,
    GameSessionStatus,
    MatchStatus,
    MordoboiMatchStatus,
    NotificationType,
    PenaltyMatchStatus,
    TacticoMatchStatus,
)
from app.models.game import GameSession
from app.models.match import Match
from app.models.mordoboi import MordoboiMatch
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
    ClubSeasonOut,
    ClubSeasonRowOut,
)
from app.services.club_budget_service import credit_club_budget
from app.services.club_emblem_service import emblem_out
from app.services.club_service import _get_membership, _lock_club
from app.services.game_config_service import get_config
from app.services.notification_service import notify

TABLE_SIZE = 20
PODIUM_SIZE = 3
DIVISION_NAMES = ["Бронзовая лига", "Серебряная лига", "Золотая лига"]
TOP_DIVISION = len(DIVISION_NAMES) - 1
# Seasons are counted in whole league weeks from this Monday.
SEASON_EPOCH = date(2024, 1, 1)


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
    for user_col in (MordoboiMatch.user_id, MordoboiMatch.opponent_user_id):
        await add("games", user_col, MordoboiMatch.resolved_at, MordoboiMatch.status == MordoboiMatchStatus.finished)
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


async def compute_table(
    db: AsyncSession, week_start: date, config, division: Optional[int] = None,
) -> list[_ClubTally]:
    """Clubs with points > 0, best first (ties: older club first) — of one
    division (the clubs' current one) when `division` is given."""
    start, end = week_bounds(week_start)
    in_division: Optional[set[int]] = None
    if division is not None:
        in_division = set((await db.execute(
            select(Club.id).where(Club.league_division == division, Club.is_disbanded.is_(False))
        )).scalars())
    clubs: dict[int, _ClubTally] = {}
    for (cid, uid), tally in (await _activity(db, start, end)).items():
        if in_division is not None and cid not in in_division:
            continue
        points = _member_points(tally, config)
        club = clubs.setdefault(cid, _ClubTally(club_id=cid))
        club.points += points
        club.members[uid] = points
    return sorted((c for c in clubs.values() if c.points > 0), key=lambda c: (-c.points, c.club_id))


# The screen's table of the running week, per (week, division, scoring):
# every open of «Лига клубов» recomputed the whole week's activity of every
# club (a heavy union over all game tables) — a minute-old table is fine to
# show. Settlement never reads it (it computes the closed week directly).
TABLE_CACHE_S = 60.0
_table_cache: dict[tuple, tuple[float, list[_ClubTally]]] = {}


async def _shown_table(db: AsyncSession, week_start: date, config, division: int) -> list[_ClubTally]:
    key = (
        week_start, division, config.club_league_points_game, config.club_league_points_pack,
        config.club_league_points_task, config.club_league_member_weekly_cap,
    )
    hit = _table_cache.get(key)
    now = _time.monotonic()
    if hit and now - hit[0] < TABLE_CACHE_S:
        return hit[1]
    table = await compute_table(db, week_start, config, division=division)
    if len(_table_cache) > 64:
        _table_cache.clear()
    _table_cache[key] = (now, table)
    return table


def _reward_for(rank: int, config, division: int = 0) -> int:
    rewards = config.club_league_rewards or []
    base = max(0, int(rewards[rank - 1])) if rank <= len(rewards) else 0
    pct = list(config.club_league_division_reward_pct or [])
    multiplier = int(pct[division]) if division < len(pct) else 100
    return base * max(0, multiplier) // 100


def season_week_index(week: date, config) -> tuple[int, int]:
    """(season number, 0-based week within it) of a league week."""
    weeks = max(1, config.club_league_season_weeks)
    n = (week - SEASON_EPOCH).days // 7
    return n // weeks, n % weeks


def season_weeks_of(week: date, config) -> list[date]:
    """Every league week of the season `week` belongs to, oldest first."""
    _season, offset = season_week_index(week, config)
    first = week - timedelta(days=7 * offset)
    return [first + timedelta(days=7 * i) for i in range(max(1, config.club_league_season_weeks))]


def _division_moves(ranked: list[tuple[int, int]], division: int, config) -> dict[int, int]:
    """club_id -> +1/-1 for a division's final standings [(club_id, points)], best first."""
    moves: dict[int, int] = {}
    if division < TOP_DIVISION:
        for club_id, points in ranked[: max(0, config.club_league_promote_count)]:
            if points > 0:
                moves[club_id] = 1
    if division > 0:
        count = min(max(0, config.club_league_relegate_count), len(ranked) // 2)
        for club_id, _points in ranked[len(ranked) - count:] if count else []:
            moves.setdefault(club_id, -1)
    return moves


async def _season_points(db: AsyncSession, weeks: list[date], division: int) -> dict[int, int]:
    """Settled season points per club of a division (results earned in it)."""
    rows = await db.execute(
        select(ClubLeagueResult.club_id, func.sum(ClubLeagueResult.points))
        .where(ClubLeagueResult.week_start.in_(weeks), ClubLeagueResult.division == division)
        .group_by(ClubLeagueResult.club_id)
    )
    return {cid: int(total or 0) for cid, total in rows.all()}


async def _division_clubs(db: AsyncSession, division: int) -> list[int]:
    return list((await db.execute(
        select(Club.id).where(Club.league_division == division, Club.is_disbanded.is_(False)).order_by(Club.id)
    )).scalars())


async def _settle_season(db: AsyncSession, last_week: date, config) -> None:
    """Final standings, promotion and relegation for the season ending with
    `last_week` (called inside settle_due's transaction, after its results)."""
    weeks = season_weeks_of(last_week, config)
    moved: list[tuple[int, int, int]] = []  # (club_id, from, to)
    for division in range(len(DIVISION_NAMES)):
        points = await _season_points(db, weeks, division)
        ranked = sorted(((cid, points.get(cid, 0)) for cid in await _division_clubs(db, division)),
                        key=lambda r: (-r[1], r[0]))
        moves = _division_moves(ranked, division, config)
        for rank, (club_id, pts) in enumerate(ranked, start=1):
            move = moves.get(club_id, 0)
            db.add(ClubSeasonResult(
                season_end_week=last_week, club_id=club_id, division=division, rank=rank, points=pts, moved=move,
            ))
            if move:
                moved.append((club_id, division, division + move))
    await db.flush()
    for club_id, old, new in moved:
        club = await _lock_club(db, club_id)
        club.league_division = new
        db.add(club)
        member_ids = (await db.execute(select(ClubMember.user_id).where(ClubMember.club_id == club_id))).scalars().all()
        for uid in member_ids:
            if new > old:
                await notify(
                    db, uid, NotificationType.club_league_promoted, "🏆 Клуб поднялся!",
                    f"«{club.name}» выходит в {DIVISION_NAMES[new]} — призы недели там больше",
                    related_object_type="club", related_object_id=club_id,
                )
            else:
                await notify(
                    db, uid, NotificationType.club_league_relegated, "Клуб опустился в лиге",
                    f"«{club.name}» переходит в {DIVISION_NAMES[new]}. Новый сезон — новый шанс!",
                    related_object_type="club", related_object_id=club_id,
                )


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
    for division in range(len(DIVISION_NAMES)):
        for rank, row in enumerate(await compute_table(db, week, config, division=division), start=1):
            reward = _reward_for(rank, config, division)
            db.add(ClubLeagueResult(
                week_start=week, club_id=row.club_id, rank=rank, points=row.points, reward=reward, division=division,
            ))
            if reward <= 0:
                continue
            club = await _lock_club(db, row.club_id)
            await credit_club_budget(
                db, club, reward, ClubBudgetTransactionType.league_reward,
                f"{DIVISION_NAMES[division]}: {rank} место ({week.strftime('%d.%m')})", related_object_type="club_league_week",
            )
            member_ids = (await db.execute(select(ClubMember.user_id).where(ClubMember.club_id == row.club_id))).scalars().all()
            for uid in member_ids:
                await notify(
                    db, uid, NotificationType.club_league_reward, "Лига клубов: итоги недели",
                    f"Клуб «{club.name}» занял {rank} место в «{DIVISION_NAMES[division]}» ({row.points} очк.) "
                    f"и получил {reward} монет в бюджет!",
                    related_object_type="club", related_object_id=row.club_id,
                )
            rewarded += 1
    await db.flush()
    _season, offset = season_week_index(week, config)
    if offset == max(1, config.club_league_season_weeks) - 1:
        await _settle_season(db, week, config)
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


async def _last_week(
    db: AsyncSession, week: date, my_club_id: Optional[int], division: int = 0,
) -> Optional[ClubLeagueLastWeekOut]:
    marker = await db.get(ClubLeagueWeek, week)
    if marker is None or marker.is_bootstrap:
        return None
    results = (
        await db.execute(
            select(ClubLeagueResult)
            .where(
                ClubLeagueResult.week_start == week,
                or_(
                    (ClubLeagueResult.rank <= PODIUM_SIZE) & (ClubLeagueResult.division == division),
                    ClubLeagueResult.club_id == my_club_id,
                ),
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
    my_club = await db.get(Club, my_club_id) if my_club_id else None
    division = my_club.league_division if my_club else 0

    table = await _shown_table(db, week, config, division) if config.club_league_enabled else []
    ranked = [(rank, row) for rank, row in enumerate(table, start=1)]
    shown = [(rank, row.club_id, row.points, _reward_for(rank, config, division)) for rank, row in ranked[:TABLE_SIZE]]
    mine = next(((rank, row) for rank, row in ranked if row.club_id == my_club_id), None)
    if mine and mine[0] > TABLE_SIZE:
        shown.append((mine[0], mine[1].club_id, mine[1].points, _reward_for(mine[0], config, division)))
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

    pct = list(config.club_league_division_reward_pct or [])
    return ClubLeagueOut(
        enabled=config.club_league_enabled,
        division=division, division_names=DIVISION_NAMES,
        division_reward_pct=int(pct[division]) if division < len(pct) else 100,
        week_start=week, ends_at=end,
        points_game=config.club_league_points_game, points_pack=config.club_league_points_pack,
        points_task=config.club_league_points_task, member_weekly_cap=config.club_league_member_weekly_cap,
        rewards=[_reward_for(i, config, division) for i in range(1, len(config.club_league_rewards or []) + 1)],
        clubs_count=len(table),
        table=rows,
        my_row=next((r for r in rows if r.club_id == my_club_id), None),
        members=members,
        last_week=await _last_week(db, week - timedelta(days=7), my_club_id, division),
        season=await _season_out(db, week, config, division, table, my_club_id) if config.club_league_enabled else None,
    )


async def _season_out(
    db: AsyncSession, week: date, config, division: int, live: list[_ClubTally], my_club_id: Optional[int],
) -> ClubSeasonOut:
    """Season-to-date standings of a division: settled weeks + this week live."""
    weeks = season_weeks_of(week, config)
    settled = await _season_points(db, [w for w in weeks if w < week], division)
    for row in live:
        settled[row.club_id] = settled.get(row.club_id, 0) + row.points
    ranked = sorted(((cid, settled.get(cid, 0)) for cid in await _division_clubs(db, division)), key=lambda r: (-r[1], r[0]))
    moves = _division_moves(ranked, division, config)
    entries = [(rank, cid, pts) for rank, (cid, pts) in enumerate(ranked, start=1)]
    shown = entries[:TABLE_SIZE]
    mine = next((e for e in entries if e[1] == my_club_id), None)
    if mine and mine[0] > TABLE_SIZE:
        shown.append(mine)
    clubs = {c.id: c for c in (await db.execute(select(Club).where(Club.id.in_([e[1] for e in shown] or [0])))).scalars()}
    rows = [
        ClubSeasonRowOut(
            rank=rank, club_id=cid, name=clubs[cid].name, logo_shape=clubs[cid].logo_shape,
            logo_color=clubs[cid].logo_color, emblem=emblem_out(clubs[cid]), points=pts,
            zone={1: "up", -1: "down"}.get(moves.get(cid, 0)),
        )
        for rank, cid, pts in shown if cid in clubs
    ]
    _season, offset = season_week_index(week, config)
    _start, season_end = week_bounds(weeks[-1])
    return ClubSeasonOut(
        weeks=len(weeks), week_of_season=offset + 1, ends_at=season_end,
        promote_count=config.club_league_promote_count if division < TOP_DIVISION else 0,
        relegate_count=config.club_league_relegate_count if division > 0 else 0,
        standings=rows, my_row=next((r for r in rows if r.club_id == my_club_id), None),
    )

