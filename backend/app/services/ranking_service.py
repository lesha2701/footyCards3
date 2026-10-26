from datetime import date
from typing import Optional

from sqlalchemy import and_, func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.models.card import UserCard
from app.models.user import User
from app.schemas.badge import BadgeOut
from app.schemas.ranking import RankingEntry, RankingMetric, RankingOut

_LEAGUE_RATING_EXPR = (User.arena_rating + User.tactics_rating + User.penalty_rating).label("league_rating")

_DIRECT_COLUMNS = {
    RankingMetric.arena_rating: User.arena_rating,
    RankingMetric.matches_won: User.matches_won,
    RankingMetric.referral_count: User.referral_count,
    RankingMetric.tactics_rating: User.tactics_rating,
    RankingMetric.penalty_rating: User.penalty_rating,
    RankingMetric.stratego_rating: User.stratego_rating,
    RankingMetric.stratego_puzzles: User.stratego_puzzles_solved,
    RankingMetric.mordoboi_rating: User.mordoboi_rating,
    RankingMetric.kontra_rating: User.kontra_rating,
    RankingMetric.league_rating: _LEAGUE_RATING_EXPR,
}


WEEKLY_METRICS = frozenset({RankingMetric.games_week, RankingMetric.stars_week, RankingMetric.referrals_week})


def _week_counts(metric: RankingMetric, week_start: date):
    """Subquery (uid, n): the user's games / Stars spent / referrals that
    count in the week starting `week_start`."""
    from app.models.game import GameSession
    from app.models.pack import StarsInvoice
    from app.models.transaction import CoinTransaction
    from app.models.enums import TransactionType
    from app.services.admin_analytics_service import MODE_SOURCES
    from app.services.club_league_service import week_bounds

    start, end = week_bounds(week_start)
    if metric == RankingMetric.stars_week:
        return (
            select(StarsInvoice.user_id.label("uid"), func.sum(StarsInvoice.stars_amount).label("n"))
            .where(StarsInvoice.completed_at >= start, StarsInvoice.completed_at < end)
            .group_by(StarsInvoice.user_id)
            .subquery()
        )
    if metric == RankingMetric.referrals_week:
        # A referral counts when it is rewarded (the friend played on
        # referral_active_days days — referral_service.check_friend), never at sign-up,
        # so throwaway accounts don't climb this board.
        friend = aliased(User)
        return (
            select(CoinTransaction.user_id.label("uid"), func.count(CoinTransaction.id).label("n"))
            .join(friend, and_(friend.id == CoinTransaction.related_object_id, friend.referred_by_id == CoinTransaction.user_id))
            .where(
                CoinTransaction.type == TransactionType.referral_reward, CoinTransaction.related_object_type == "user",
                CoinTransaction.created_at >= start, CoinTransaction.created_at < end,
            )
            .group_by(CoinTransaction.user_id)
            .subquery()
        )
    # Games: every played mini-game session plus every match / battle of the
    # game modes (season and club rows of the career modes and wheel spins
    # are not games).
    parts = [select(GameSession.user_id.label("uid")).where(GameSession.created_at >= start, GameSession.created_at < end)]
    for source in MODE_SOURCES:
        if source.key in {"career", "player_career", "manager", "wheel"}:
            continue
        for col in source.user_cols:
            q = select(col.label("uid")).select_from(source.model)
            if source.join is not None:
                q = q.join(*source.join)
            parts.append(q.where(source.ts >= start, source.ts < end, col.is_not(None)))
    games = union_all(*parts).subquery()
    return select(games.c.uid, func.count().label("n")).group_by(games.c.uid).subquery()


def ranking_statement(metric: RankingMetric, week_start: Optional[date] = None):
    """(User, value) rows of a ranking, best first (ties: the earlier
    account first). Weekly metrics count the week starting `week_start`
    (default: the current one)."""
    if metric in WEEKLY_METRICS:
        from app.services.club_league_service import week_start_for

        counts = _week_counts(metric, week_start or week_start_for())
        return (
            select(User, counts.c.n)
            .join(counts, counts.c.uid == User.id)
            .where(User.is_banned.is_(False), User.is_admin.is_(False), counts.c.n > 0)
            .order_by(counts.c.n.desc(), User.id)
        )
    return _standing_statement(metric).order_by(User.id)


def _start_value(column) -> int:
    default = column.property.columns[0].default
    return int(default.arg) if default is not None and isinstance(default.arg, int) else 0


def starting_value(metric: RankingMetric) -> int:
    """What a player who never played has (ratings start at 1000 etc.)."""
    if metric == RankingMetric.league_rating:
        return sum(_start_value(c) for c in (User.arena_rating, User.tactics_rating, User.penalty_rating))
    column = _DIRECT_COLUMNS.get(metric)
    return _start_value(column) if column is not None and hasattr(column, "property") else 0


async def top_rows(db: AsyncSession, metric: RankingMetric, limit: int, week_start: Optional[date] = None) -> list:
    """The first `limit` (User, value) rows above the starting value — a
    rating nobody has played yet ranks nobody."""
    floor = starting_value(metric)
    rows = (await db.execute(ranking_statement(metric, week_start).limit(limit))).all()
    return [(user, int(value or 0)) for user, value in rows if (value or 0) > floor]


def _standing_statement(metric: RankingMetric):
    if metric == RankingMetric.cards_count:
        value_expr = func.count(UserCard.id)
        stmt = (
            select(User, value_expr)
            # User.active_badge is lazy="joined" by default, which would pull
            # badges columns into this aggregate SELECT and make Postgres
            # reject the GROUP BY (badges_1.id isn't functionally dependent
            # on users.id) — selectinload replaces that with a second query
            # instead, keeping the grouped query itself to just users+count.
            .options(selectinload(User.active_badge))
            .outerjoin(UserCard, UserCard.owner_id == User.id)
            .where(User.is_banned.is_(False), User.is_admin.is_(False))
            .group_by(User.id)
            .order_by(value_expr.desc())
        )
    elif metric == RankingMetric.unique_players:
        value_expr = func.count(func.distinct(UserCard.player_id))
        stmt = (
            select(User, value_expr)
            .options(selectinload(User.active_badge))
            .outerjoin(UserCard, UserCard.owner_id == User.id)
            .where(User.is_banned.is_(False), User.is_admin.is_(False))
            .group_by(User.id)
            .order_by(value_expr.desc())
        )
    elif metric == RankingMetric.academy_level:
        # «Уровень Академии»: the sum of the building's wing levels.
        from app.models.card_path import UserAcademy

        stmt = (
            select(User, UserAcademy.total_level)
            .join(UserAcademy, UserAcademy.user_id == User.id)
            .where(User.is_banned.is_(False), User.is_admin.is_(False), UserAcademy.total_level > 0)
            .order_by(UserAcademy.total_level.desc())
        )
    elif metric == RankingMetric.base_level:
        # «Уровень базы»: the «Клубная база» buildings plus the «Академия» wings.
        from app.models.card_path import UserAcademy
        from app.models.club_base import UserClubBase

        value_expr = func.coalesce(UserClubBase.total_level, 0) + func.coalesce(UserAcademy.total_level, 0)
        stmt = (
            select(User, value_expr)
            .outerjoin(UserClubBase, UserClubBase.user_id == User.id)
            .outerjoin(UserAcademy, UserAcademy.user_id == User.id)
            .where(User.is_banned.is_(False), User.is_admin.is_(False), value_expr > 0)
            .order_by(value_expr.desc())
        )
    elif metric == RankingMetric.academy_prestige:
        # «Престиж Академии»: total prestige tiers of the user's copies.
        value_expr = func.coalesce(func.sum(UserCard.prestige), 0)
        stmt = (
            select(User, value_expr)
            .options(selectinload(User.active_badge))
            .join(UserCard, UserCard.owner_id == User.id)
            .where(User.is_banned.is_(False), User.is_admin.is_(False), UserCard.prestige > 0)
            .group_by(User.id)
            .order_by(value_expr.desc())
        )
    else:
        column = _DIRECT_COLUMNS[metric]
        stmt = (
            select(User, column)
            .where(User.is_banned.is_(False), User.is_admin.is_(False))
            .order_by(column.desc())
        )
    return stmt


async def get_ranking(db: AsyncSession, metric: RankingMetric, current_user: User, limit: int = 10) -> RankingOut:
    rows = (await db.execute(ranking_statement(metric))).all()

    def to_entry(rank: int, user: User, value) -> RankingEntry:
        return RankingEntry(
            rank=rank,
            user_id=user.id,
            display_name=user.full_display_name(),
            avatar_url=user.avatar_url,
            value=int(value or 0),
            active_badge=BadgeOut.model_validate(user.active_badge) if user.active_badge else None,
        )

    top = [to_entry(i + 1, user, value) for i, (user, value) in enumerate(rows[:limit])]

    me = None
    for i, (user, value) in enumerate(rows):
        if user.id == current_user.id:
            me = to_entry(i + 1, user, value)
            break

    return RankingOut(metric=metric, top=top, me=me)
