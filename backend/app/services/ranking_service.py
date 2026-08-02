from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.card import UserCard
from app.models.user import User
from app.schemas.ranking import RankingEntry, RankingMetric, RankingOut

_DIRECT_COLUMNS = {
    RankingMetric.arena_rating: User.arena_rating,
    RankingMetric.matches_won: User.matches_won,
    RankingMetric.referral_count: User.referral_count,
    RankingMetric.tactics_rating: User.tactics_rating,
}


async def get_ranking(db: AsyncSession, metric: RankingMetric, current_user: User, limit: int = 10) -> RankingOut:
    if metric == RankingMetric.cards_count:
        value_expr = func.count(UserCard.id)
        stmt = (
            select(User, value_expr)
            .outerjoin(UserCard, UserCard.owner_id == User.id)
            .where(User.is_banned.is_(False))
            .group_by(User.id)
            .order_by(value_expr.desc())
        )
    elif metric == RankingMetric.unique_players:
        value_expr = func.count(func.distinct(UserCard.player_id))
        stmt = (
            select(User, value_expr)
            .outerjoin(UserCard, UserCard.owner_id == User.id)
            .where(User.is_banned.is_(False))
            .group_by(User.id)
            .order_by(value_expr.desc())
        )
    else:
        column = _DIRECT_COLUMNS[metric]
        stmt = select(User, column).where(User.is_banned.is_(False)).order_by(column.desc())

    rows = (await db.execute(stmt)).all()

    def to_entry(rank: int, user: User, value) -> RankingEntry:
        return RankingEntry(rank=rank, user_id=user.id, display_name=user.full_display_name(), avatar_url=user.avatar_url, value=int(value or 0))

    top = [to_entry(i + 1, user, value) for i, (user, value) in enumerate(rows[:limit])]

    me = None
    for i, (user, value) in enumerate(rows):
        if user.id == current_user.id:
            me = to_entry(i + 1, user, value)
            break

    return RankingOut(metric=metric, top=top, me=me)
