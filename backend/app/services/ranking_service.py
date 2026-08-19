from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    RankingMetric.league_rating: _LEAGUE_RATING_EXPR,
}


async def get_ranking(db: AsyncSession, metric: RankingMetric, current_user: User, limit: int = 10) -> RankingOut:
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
    else:
        column = _DIRECT_COLUMNS[metric]
        stmt = (
            select(User, column)
            .where(User.is_banned.is_(False), User.is_admin.is_(False))
            .order_by(column.desc())
        )

    rows = (await db.execute(stmt)).all()

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
