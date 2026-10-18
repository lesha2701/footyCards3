"""«Клубные войны»: once a league week, at `club_war_start_weekday` /
`club_war_start_hour` (app timezone), every club with at least
`club_war_min_members` members is paired with the club closest to it by war
rating (Elo, `Club.war_rating`) for `club_war_duration_hours`. During the
window each member's activity — the same games / paid packs / tasks the
club league counts, at the league's point values, capped per member by
`club_war_member_cap` — scores war points for their club.

No scheduler of its own: `sweep` (bot every few minutes via
/internal/clubs/wars/sweep, and lazily when anyone opens the war screen)
pairs the week once — the `club_war_rounds` primary key makes a concurrent
second pairing roll back — and settles every finished war under its row
lock: budget prizes, a reward every member of the winner claims, Elo update
and notifications."""
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.timeutil import app_timezone
from app.models.club import Club, ClubMember
from app.models.club_war import ClubWar, ClubWarRound
from app.models.enums import ClubBudgetTransactionType, NotificationType
from app.models.game_config import GameConfig
from app.models.user import User
from app.schemas.club_war import ClubWarMemberOut, ClubWarOut, ClubWarSideOut, ClubWarSummaryOut
from app.services.club_budget_service import credit_club_budget
from app.services.club_emblem_service import emblem_out
from app.services.club_league_service import _activity, week_start_for
from app.services.club_reward_service import create_grant
from app.services.game_config_service import get_config
from app.services.notification_service import notify
from app.services.reward_bundle_service import Bundle

ELO_K = 32
HISTORY = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def window_for(week: date, config: GameConfig) -> tuple[datetime, datetime]:
    day = week + timedelta(days=max(0, min(6, config.club_war_start_weekday)))
    start = datetime.combine(day, time(hour=max(0, min(23, config.club_war_start_hour))), tzinfo=app_timezone())
    start = start.astimezone(timezone.utc)
    return start, start + timedelta(hours=max(1, config.club_war_duration_hours))


def _member_points(tally, config: GameConfig) -> int:
    raw = (
        tally.games * config.club_league_points_game
        + tally.packs * config.club_league_points_pack
        + tally.tasks * config.club_league_points_task
    )
    return min(raw, max(0, config.club_war_member_cap))


async def _scores(db: AsyncSession, war: ClubWar, config: GameConfig) -> dict[int, dict[int, tuple]]:
    """club_id -> {user_id: (games, packs, tasks, points)} for the war window so far."""
    end = min(_aware(war.ends_at), _now())
    out: dict[int, dict[int, tuple]] = {war.club_a_id: {}, war.club_b_id: {}}
    for club_id in (war.club_a_id, war.club_b_id):
        for (_cid, uid), tally in (await _activity(db, _aware(war.starts_at), end, club_id=club_id)).items():
            out[club_id][uid] = (tally.games, tally.packs, tally.tasks, _member_points(tally, config))
    return out


def _total(per_member: dict[int, tuple]) -> int:
    return sum(v[3] for v in per_member.values())


async def _notify_club(db: AsyncSession, club_id: int, type_: NotificationType, title: str, body: str) -> None:
    for uid in (await db.execute(select(ClubMember.user_id).where(ClubMember.club_id == club_id))).scalars().all():
        await notify(db, uid, type_, title, body, related_object_type="club", related_object_id=club_id)


async def start_due(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """Pairs this week's wars once its start time has come. Returns the
    number of wars created (0 when already paired or not yet time)."""
    config = await get_config(db)
    if not config.club_war_enabled:
        return 0
    now = now or _now()
    week = week_start_for(now)
    starts_at, ends_at = window_for(week, config)
    if now < starts_at or now >= ends_at or await db.get(ClubWarRound, week) is not None:
        return 0
    try:
        db.add(ClubWarRound(week_start=week, starts_at=starts_at, ends_at=ends_at))
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return 0

    counts = (
        select(ClubMember.club_id, func.count(ClubMember.id).label("cnt")).group_by(ClubMember.club_id).subquery()
    )
    clubs = (await db.execute(
        select(Club).join(counts, counts.c.club_id == Club.id)
        .where(Club.is_disbanded.is_(False), counts.c.cnt >= max(1, config.club_war_min_members))
        .order_by(Club.war_rating.desc(), Club.league_division.desc(), Club.id)
    )).scalars().all()
    created = 0
    # Neighbours by rating fight each other; an odd club out sits this week out.
    for a, b in zip(clubs[0::2], clubs[1::2]):
        db.add(ClubWar(week_start=week, club_a_id=a.id, club_b_id=b.id, starts_at=starts_at, ends_at=ends_at))
        created += 1
        hours = config.club_war_duration_hours
        await _notify_club(db, a.id, NotificationType.club_war_started, "⚔️ Война началась!",
                           f"«{a.name}» против «{b.name}» — {hours} ч. Каждая игра, пак и задание приносят очки!")
        await _notify_club(db, b.id, NotificationType.club_war_started, "⚔️ Война началась!",
                           f"«{b.name}» против «{a.name}» — {hours} ч. Каждая игра, пак и задание приносят очки!")
    await db.commit()
    return created


def _elo(rating_a: int, rating_b: int, score_a: float) -> tuple[int, int]:
    expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    delta = round(ELO_K * (score_a - expected_a))
    return rating_a + delta, rating_b - delta


async def settle_due(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """Settles every finished war once. Returns how many were settled."""
    config = await get_config(db)
    now = now or _now()
    due_ids = (await db.execute(
        select(ClubWar.id).where(ClubWar.status == "active", ClubWar.ends_at <= now)
    )).scalars().all()
    settled = 0
    for war_id in due_ids:
        war = (await db.execute(
            select(ClubWar).where(ClubWar.id == war_id).with_for_update().execution_options(populate_existing=True)
        )).scalar_one()
        if war.status != "active":
            await db.rollback()
            continue
        scores = await _scores(db, war, config)
        war.score_a, war.score_b = _total(scores[war.club_a_id]), _total(scores[war.club_b_id])
        war.status, war.settled_at = "finished", now
        if war.score_a != war.score_b:
            war.winner_club_id = war.club_a_id if war.score_a > war.score_b else war.club_b_id

        club_a = (await db.execute(select(Club).where(Club.id == war.club_a_id).with_for_update().execution_options(populate_existing=True))).scalar_one()
        club_b = (await db.execute(select(Club).where(Club.id == war.club_b_id).with_for_update().execution_options(populate_existing=True))).scalar_one()
        result_a = 0.5 if war.winner_club_id is None else (1.0 if war.winner_club_id == club_a.id else 0.0)
        club_a.war_rating, club_b.war_rating = _elo(club_a.war_rating, club_b.war_rating, result_a)

        for club, opponent, my, their in ((club_a, club_b, war.score_a, war.score_b), (club_b, club_a, war.score_b, war.score_a)):
            if war.winner_club_id is None:
                prize, title, text = config.club_war_draw_budget, "Война: ничья", f"Ничья с «{opponent.name}» — {my}:{their}"
            elif war.winner_club_id == club.id:
                prize, title, text = config.club_war_win_budget, "⚔️ Победа в войне!", f"«{club.name}» победил «{opponent.name}» — {my}:{their}"
            else:
                prize, title, text = config.club_war_loss_budget, "Война проиграна", f"«{opponent.name}» оказался сильнее — {my}:{their}"
            if prize > 0:
                await credit_club_budget(
                    db, club, prize, ClubBudgetTransactionType.war_reward, f"Клубная война с «{opponent.name}»",
                    related_object_type="club_war", related_object_id=war.id,
                )
                text += f". В казну +{prize}"
            await _notify_club(db, club.id, NotificationType.club_war_finished, title, text)
            if war.winner_club_id == club.id:
                await create_grant(
                    db, club.id, "war", f"Победа над «{opponent.name}»",
                    Bundle(coins=config.club_war_win_member_coins), source_ref_id=war.id, notify_members=False,
                )
        await db.commit()
        settled += 1
    return settled


async def sweep(db: AsyncSession) -> tuple[int, int]:
    settled = await settle_due(db)
    started = await start_due(db)
    return started, settled


async def war_record(db: AsyncSession, club_id: int) -> tuple[int, int]:
    """(wins, finished wars) of a club — the trophy room."""
    rows = (await db.execute(
        select(ClubWar.winner_club_id).where(
            ClubWar.status == "finished", or_(ClubWar.club_a_id == club_id, ClubWar.club_b_id == club_id),
        )
    )).scalars().all()
    return sum(1 for w in rows if w == club_id), len(rows)


def _side(club: Club, score: int, members: list[ClubWarMemberOut]) -> ClubWarSideOut:
    return ClubWarSideOut(
        club_id=club.id, name=club.name, logo_shape=club.logo_shape, logo_color=club.logo_color,
        emblem=emblem_out(club), war_rating=club.war_rating, score=score, members=members,
    )


async def get_war(db: AsyncSession, user: User) -> ClubWarOut:
    membership = (await db.execute(select(ClubMember).where(ClubMember.user_id == user.id))).scalar_one_or_none()
    if membership is None:
        raise NotFoundError("Ты не состоишь в клубе")
    # A plain int: sweep may roll back, which expires every loaded object.
    club_id = membership.club_id
    await sweep(db)
    config = await get_config(db)
    my_club = await db.get(Club, club_id)
    week = week_start_for()
    starts_at, ends_at = window_for(week, config)
    member_count = (await db.execute(select(func.count(ClubMember.id)).where(ClubMember.club_id == club_id))).scalar_one()

    war = (await db.execute(
        select(ClubWar).where(ClubWar.week_start == week, or_(ClubWar.club_a_id == club_id, ClubWar.club_b_id == club_id))
    )).scalar_one_or_none()
    history_rows = (await db.execute(
        select(ClubWar).where(
            ClubWar.status == "finished", or_(ClubWar.club_a_id == club_id, ClubWar.club_b_id == club_id),
        ).order_by(ClubWar.ends_at.desc()).limit(HISTORY)
    )).scalars().all()
    other_ids = {w.club_b_id if w.club_a_id == club_id else w.club_a_id for w in history_rows}
    names = dict((await db.execute(select(Club.id, Club.name).where(Club.id.in_(other_ids or {0})))).all())
    history = []
    for w in history_rows:
        mine_a = w.club_a_id == club_id
        history.append(ClubWarSummaryOut(
            war_id=w.id, opponent_name=names.get(w.club_b_id if mine_a else w.club_a_id, "?"),
            my_score=w.score_a if mine_a else w.score_b, opponent_score=w.score_b if mine_a else w.score_a,
            result="draw" if w.winner_club_id is None else ("win" if w.winner_club_id == club_id else "loss"),
            ended_at=w.ends_at,
        ))

    out = ClubWarOut(
        enabled=config.club_war_enabled, state="none", starts_at=starts_at, ends_at=ends_at,
        duration_hours=config.club_war_duration_hours, min_members=config.club_war_min_members,
        member_count=member_count, war_rating=my_club.war_rating,
        win_budget=config.club_war_win_budget, draw_budget=config.club_war_draw_budget,
        loss_budget=config.club_war_loss_budget, win_member_coins=config.club_war_win_member_coins,
        history=history,
    )
    if war is None:
        out.state = "upcoming" if _now() < starts_at else "none"
        if _now() >= ends_at:
            out.starts_at, out.ends_at = window_for(week + timedelta(days=7), config)
            out.state = "upcoming"
        return out

    names_by_id = dict((await db.execute(
        select(User.id, func.coalesce(User.username, User.first_name)).join(ClubMember, ClubMember.user_id == User.id)
        .where(ClubMember.club_id.in_([war.club_a_id, war.club_b_id]))
    )).all())
    if war.status == "active":
        per_club = await _scores(db, war, config)
    else:
        per_club = None
    my_is_a = war.club_a_id == club_id
    opponent = await db.get(Club, war.club_b_id if my_is_a else war.club_a_id)

    def members_of(cid: int) -> list[ClubWarMemberOut]:
        if per_club is None:
            return []
        return sorted(
            (ClubWarMemberOut(user_id=uid, name=names_by_id.get(uid) or f"#{uid}", games=g, packs=p, tasks=t, points=pts)
             for uid, (g, p, t, pts) in per_club[cid].items()),
            key=lambda m: -m.points,
        )

    my_score = _total(per_club[club_id]) if per_club else (war.score_a if my_is_a else war.score_b)
    their_score = _total(per_club[opponent.id]) if per_club else (war.score_b if my_is_a else war.score_a)
    out.state = "active" if war.status == "active" else "finished"
    out.war_id = war.id
    out.starts_at, out.ends_at = _aware(war.starts_at), _aware(war.ends_at)
    out.me = _side(my_club, my_score, members_of(club_id))
    out.opponent = _side(opponent, their_score, members_of(opponent.id))
    if war.status == "finished":
        out.result = "draw" if war.winner_club_id is None else ("win" if war.winner_club_id == club_id else "loss")
    return out
